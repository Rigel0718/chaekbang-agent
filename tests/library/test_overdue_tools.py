"""[agent/admin] 연체 목록 tool, 안내문 틀 초안 tool, 회원 값은 LLM에 가지 않음(카나리아)."""

import json
from datetime import date, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import ToolResult
from app.agent.models import AgentStep
from app.agent.runner import ResultEvent, run
from app.core import clock
from app.features.children.analytics import admin_extension
from app.library.admin_agent import build_admin_profiles
from app.library.approval import ApprovalStatus
from app.library.models.library import LoanMode
from app.library.overdue_tools import DRAFT_OVERDUE_NOTICE, LIST_OVERDUE_LOANS
from app.library.schemas.overdue_notice import OverdueLoanList, TemplateWrite
from app.library.services import overdue_notices as svc
from tests.agent.fakes import FakeLlm, call, tool_turn
from tests.conftest import Tenant
from tests.helpers import add_held_book, add_loan, insert
from tests.library.chat_helpers import LlmSlot, parse_sse
from tests.library.test_admin_agent import _paths

TODAY = date(2026, 11, 21)
BODY = "{이름}님, '{서명}'의 반납 예정일({반납예정일})이 {연체일수}일 지났어요. {도서관}"
CANARY = {"name": "카나리아회원", "member_number": "CANARY0001", "phone": "01099990000"}

# 연체 목록 tool 결과의 필드. 회원 값을 넣지 않는다. 필드를 더하면 개인정보가 아닌지 보고 고친다.
ALLOWED_LIST_FIELDS = {
    "total",
    "shown",
    "truncated",
    "has_template",
    "items[].title",
    "items[].accession_number",
    "items[].due_on",
    "items[].overdue_days",
}


@pytest.fixture(autouse=True)
def _today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "today", lambda: TODAY)


async def _overdue(
    session: AsyncSession,
    library_id: int,
    member: Any,
    title: str,
    due_on: date = date(2026, 11, 10),
) -> Any:
    book = await add_held_book(session, library_id, title=title)
    holding = (
        (
            await session.execute(
                text("SELECT * FROM holdings WHERE library_book_id = :id"), {"id": book["id"]}
            )
        )
        .mappings()
        .one()
    )
    return await add_loan(
        session, holding, member, loaned_on=due_on - timedelta(days=14), due_on=due_on
    )


async def _member(session: AsyncSession, library_id: int, **values: Any) -> Any:
    defaults = {"member_number": "M0001", "name": "김이용", "phone": None}
    return await insert(session, "members", library_id=library_id, **{**defaults, **values})


def _results(llm: FakeLlm, request: int = 1) -> list[ToolResult]:
    return [m for m in llm.requests[request]["messages"] if isinstance(m, ToolResult)]


def answer(message: str = "승인 대기로 올렸어요.", unsupported: str | None = None) -> Any:
    return tool_turn(
        call("submit_answer", {"message": message, "unsupported": unsupported}, "answer")
    )


def draft(template: str = BODY, id: str = "c1") -> Any:
    return tool_turn(call("draft_overdue_notice", {"template": template}, id))


def listing() -> Any:
    return tool_turn(call("list_overdue_loans", {}))


async def _run_admin(session: AsyncSession, llm: FakeLlm, library_id: int) -> list[Any]:
    profile = build_admin_profiles([admin_extension()])[LoanMode.INTERNAL]
    return [
        e
        async for e in run(
            session=session,
            llm=llm,
            profile=profile,
            library_id=library_id,
            user_text="연체 안내문 만들어 줘",
        )
    ]


# --- 연체 목록 tool ---


def test_list_result_fields_allowlist() -> None:
    """[agent/admin] 연체 목록 tool / 결과 필드 (허용 목록)"""
    schema = OverdueLoanList.model_json_schema()
    assert _paths(schema, schema.get("$defs", {})) == ALLOWED_LIST_FIELDS
    assert LIST_OVERDUE_LOANS.record_fields == ()


async def test_list_returns_only_book_fields(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/admin] 연체 목록 tool / 결과 필드"""
    who = await _member(session, library_a.id, **CANARY)
    await _overdue(session, library_a.id, who, "공룡 대백과")
    llm = FakeLlm([listing(), answer("연체는 1건이에요.")])
    await _run_admin(session, llm, library_a.id)
    [result] = _results(llm)
    body = json.loads(result.content)
    assert not result.is_error
    assert (body["total"], body["shown"], body["truncated"], body["has_template"]) == (
        1,
        1,
        False,
        False,
    )
    assert body["items"] == [
        {
            "title": "공룡 대백과",
            "accession_number": body["items"][0]["accession_number"],
            "due_on": "2026-11-10",
            "overdue_days": 11,
        }
    ]
    for value in CANARY.values():
        assert value not in result.content


async def test_list_is_truncated(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/admin] 연체 목록 tool / 잘린 목록"""
    for index in range(25):
        who = await _member(session, library_a.id, member_number=f"M{index:04d}")
        await _overdue(session, library_a.id, who, f"책 {index}")
    llm = FakeLlm([listing(), answer("25건이에요.")])
    await _run_admin(session, llm, library_a.id)
    body = json.loads(_results(llm)[0].content)
    assert (body["total"], body["shown"], body["truncated"], len(body["items"])) == (
        25,
        20,
        True,
        20,
    )


async def test_list_without_template(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/admin] 연체 목록 tool / 틀 없는 기관"""
    who = await _member(session, library_a.id)
    await _overdue(session, library_a.id, who, "공룡")
    llm = FakeLlm([listing(), answer("1건이에요.")])
    await _run_admin(session, llm, library_a.id)
    body = json.loads(_results(llm)[0].content)
    assert body["has_template"] is False
    assert body["total"] == 1
    template = await svc.create_template(session, library_a.id, None, TemplateWrite(body=BODY))
    await svc.submit_template(session, library_a.id, template.id)
    await svc.approve_template(session, library_a.id, template.id, library_a.admin["id"])
    llm = FakeLlm([listing(), answer("1건이에요.")])
    await _run_admin(session, llm, library_a.id)
    assert json.loads(_results(llm)[0].content)["has_template"] is True


# --- 안내문 틀 초안 tool ---


async def test_draft_saves_pending(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/admin] 안내문 틀 초안 tool / 틀 저장"""
    who = await _member(session, library_a.id)
    await _overdue(session, library_a.id, who, "공룡")
    llm = FakeLlm([draft(), answer()])
    await _run_admin(session, llm, library_a.id)
    [result] = _results(llm)
    body = json.loads(result.content)
    assert not result.is_error
    assert (body["status"], body["overdue_count"]) == ("pending_approval", 1)
    assert set(body) == {"template_id", "status", "overdue_count", "note"}
    template = await svc.get_template(session, library_a.id, body["template_id"])
    assert template.status == ApprovalStatus.PENDING_APPROVAL
    assert template.body == BODY
    assert template.created_by is None
    assert "김이용" not in result.content


@pytest.mark.parametrize(
    "template",
    [
        "{이름}님 {서명} {반납예정일} {전화번호}로 연락 주세요",
        "{이름}님 {서명} 반납해 주세요",
        "{서명} {반납예정일} 문의 010-1234-5678",
        "{서명} {반납예정일} " + "가" * 300,
    ],
)
async def test_draft_rule_errors(session: AsyncSession, library_a: Tenant, template: str) -> None:
    """[agent/admin] 안내문 틀 초안 tool / 모르는 자리표시 (내용·개인정보 규칙 위반은 오류 결과)"""
    llm = FakeLlm([draft(template), answer("못 올렸어요")])
    await _run_admin(session, llm, library_a.id)
    [result] = _results(llm)
    assert result.is_error
    assert "010-1234-5678" not in result.content
    assert await svc.list_templates(session, library_a.id) == []


async def test_draft_records_no_input(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/admin] 안내문 틀 초안 tool / 실행 기록"""
    secret = "{서명} {반납예정일} 비밀문장XYZ"
    llm = FakeLlm([draft(secret), answer()])
    await _run_admin(session, llm, library_a.id)
    [step] = await session.scalars(
        select(AgentStep).where(AgentStep.name == "draft_overdue_notice")
    )
    assert not step.detail
    runs = await session.execute(text("SELECT row_to_json(r)::text FROM agent_runs r"))
    steps = await session.execute(text("SELECT row_to_json(s)::text FROM agent_steps s"))
    dumped = " ".join(r[0] for r in [*runs, *steps])
    assert "비밀문장XYZ" not in dumped
    assert DRAFT_OVERDUE_NOTICE.record_fields == ()


# --- 카나리아 ---


async def test_canary_member_values_never_reach_llm_or_records(
    admin_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/admin] 회원 값은 LLM에 가지 않음 / 카나리아 회원"""
    who = await _member(session, library_a.id, **CANARY)
    await _overdue(session, library_a.id, who, "공룡 대백과")
    fake_llm.script(
        listing(),
        draft(id="c2"),
        answer("연체는 1건이에요. 승인 대기로 올렸어요."),
    )
    res = await admin_client.post(
        "/admin-agent/messages", json={"message": "연체된 책 보고 안내문 만들어 줘"}
    )
    assert res.status_code == 200
    assert [e.name for e in parse_sse(res.text)][-1] == "done"
    assert fake_llm.calls == 3

    sent = repr(fake_llm.llm.requests)
    tables = (
        "agent_runs",
        "agent_steps",
        "chat_messages",
        "chat_sessions",
        "overdue_notice_templates",
    )
    dumped = []
    for table in tables:
        rows = await session.execute(text(f"SELECT row_to_json(t)::text FROM {table} t"))
        dumped.extend(r[0] for r in rows)
    stored = " ".join(dumped)
    assert "{이름}" in stored  # 틀은 저장됐다
    for value in CANARY.values():
        assert value not in sent, value
        assert value not in stored, value

    # 같은 값이 관리자 목록에는 나온다(검사가 헛돌지 않는지 확인).
    [template] = await svc.list_templates(session, library_a.id)
    await svc.approve_template(session, library_a.id, template.id, library_a.admin["id"])
    listed = await admin_client.get("/overdue-notices/today")
    for value in CANARY.values():
        assert value in listed.text


# --- 결과 사건 ---


async def test_draft_result_event(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/admin] 초안 결과 사건 / 안내문 틀 초안"""
    who = await _member(session, library_a.id)
    await _overdue(session, library_a.id, who, "공룡")
    llm = FakeLlm([draft(), answer()])
    events = await _run_admin(session, llm, library_a.id)
    [value] = [e.value for e in events if isinstance(e, ResultEvent)]
    body = json.loads(_results(llm)[0].content)
    assert value.model_dump(mode="json") == {
        "kind": "draft",
        "draft": "template",
        "id": body["template_id"],
    }
