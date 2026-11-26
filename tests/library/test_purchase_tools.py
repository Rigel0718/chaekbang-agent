"""[agent/admin] 구매 후보 tool, 구매 요청서 초안 tool, 구매 요청서 tool의 회원 값(카나리아).

가짜 LLM으로 운영 에이전트 실행을 돌린다. 정가 조회기는 가짜로 바꿔 끼우고 호출이 없는지 본다.
"""

import json
from datetime import UTC, date, datetime
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
from app.library.api.purchase_requests import get_list_prices
from app.library.approval import ApprovalStatus
from app.library.models.library import LoanMode
from app.library.purchase_tools import DRAFT_PURCHASE_REQUEST, LIST_PURCHASE_CANDIDATES
from app.library.schemas.purchase_candidates import ImportedPopular, LoanPopular, WishCandidate
from app.library.services import purchase_requests as svc
from app.main import app
from tests.agent.fakes import FakeLlm, call, tool_turn
from tests.conftest import Tenant
from tests.helpers import (
    VALID_ISBN,
    VALID_ISBN_2,
    VALID_ISBN_3,
    add_held_book,
    add_loan,
    add_member,
)
from tests.library.chat_helpers import LlmSlot, parse_sse
from tests.purchase_helpers import FakeListPrices, add_book_request

TODAY = date(2026, 11, 19)
SYNCED = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
CANARY = {"name": "카나리아회원", "member_number": "CANARY0001"}


@pytest.fixture(autouse=True)
def _today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "today", lambda: TODAY)


def _results(llm: FakeLlm, request: int = 1) -> list[ToolResult]:
    return [m for m in llm.requests[request]["messages"] if isinstance(m, ToolResult)]


def answer(message: str = "승인 대기로 올렸어요.", unsupported: str | None = None) -> Any:
    return tool_turn(
        call("submit_answer", {"message": message, "unsupported": unsupported}, "answer")
    )


def candidates(period: str | None = None, id: str = "c1") -> Any:
    return tool_turn(call("list_purchase_candidates", {"period": period}, id))


def draft(*items: tuple[str, int], period: str | None = None, id: str = "c2") -> Any:
    body = {
        "title": "12월 보충 구매",
        "note": None,
        "period": period,
        "items": [{"isbn": i, "quantity": q, "reason": "신청 2건"} for i, q in items],
    }
    return tool_turn(call("draft_purchase_request", body, id))


async def _run(
    session: AsyncSession, llm: FakeLlm, library_id: int, mode: LoanMode = LoanMode.INTERNAL
) -> list[Any]:
    profile = build_admin_profiles([admin_extension()])[mode]
    return [
        e
        async for e in run(
            session=session, llm=llm, profile=profile, library_id=library_id, user_text="요청서"
        )
    ]


async def _popular_book(
    session: AsyncSession, library_id: int, member: Any, isbn: str, status: str = "available"
) -> None:
    """최근 90일에 두 번 빌린 책(사본 하나, 상태 `status`)."""
    book = await add_held_book(session, library_id, status, isbn=isbn, title="인기 책")
    holding = (
        (
            await session.execute(
                text("SELECT * FROM holdings WHERE library_book_id = :b"), {"b": book["id"]}
            )
        )
        .mappings()
        .one()
    )
    await add_loan(
        session, holding, member, loaned_on=date(2026, 11, 1), returned_on=date(2026, 11, 3)
    )
    await add_loan(
        session, holding, member, loaned_on=date(2026, 11, 5), returned_on=date(2026, 11, 7)
    )


async def _setup(session: AsyncSession, library_id: int) -> Any:
    """희망도서 VALID_ISBN(신청 2건)과 인기 책 VALID_ISBN_2. 신청 회원 하나는 카나리아다."""
    canary = await add_member(session, library_id, CANARY["member_number"], name=CANARY["name"])
    other = await add_member(session, library_id, "M0002")
    await add_book_request(
        session, library_id, member_id=canary["id"], title="희망 책", isbn=VALID_ISBN
    )
    await add_book_request(
        session, library_id, member_id=other["id"], title="희망 책", isbn=VALID_ISBN
    )
    await _popular_book(session, library_id, other, VALID_ISBN_2)
    return canary


# --- 구매 후보 tool ---


def test_candidate_row_fields_allowlist() -> None:
    """[agent/admin] 구매 후보 tool / 결과 필드 (허용 목록. 더할 때는 회원 값·가격이 아닌지 본다)"""
    assert set(WishCandidate.model_fields) == {"isbn", "title", "author", "request_count"}
    assert set(LoanPopular.model_fields) == {
        "isbn",
        "title",
        "author",
        "loans",
        "copies",
        "on_loan",
    }
    assert set(ImportedPopular.model_fields) == {
        "isbn",
        "title",
        "author",
        "copies",
        "on_loan",
        "synced_at",
    }
    assert LIST_PURCHASE_CANDIDATES.record_fields == ("period",)


async def test_candidates_tool_result(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/admin] 구매 후보 tool / 결과 필드"""
    await _setup(session, library_a.id)
    llm = FakeLlm([candidates(), answer("희망도서 1종이에요.")])
    await _run(session, llm, library_a.id)
    [result] = _results(llm)
    assert not result.is_error
    body = json.loads(result.content)
    assert body["wishes"] == [
        {"isbn": VALID_ISBN, "title": "희망 책", "author": None, "request_count": 2}
    ]
    assert body["popular"][0]["isbn"] == VALID_ISBN_2 and body["popular"][0]["loans"] == 2
    assert "price" not in result.content and "amount" not in result.content
    for value in CANARY.values():
        assert value not in result.content


async def test_candidates_tool_external(session: AsyncSession, library_b: Tenant) -> None:
    """[agent/admin] 구매 후보 tool / 외부 대출 기관"""
    await add_held_book(
        session, library_b.id, "on_loan", "on_loan", isbn=VALID_ISBN_3, synced=[SYNCED, SYNCED]
    )
    llm = FakeLlm([candidates(), answer("가져온 파일 기준이에요.")])
    await _run(session, llm, library_b.id, LoanMode.EXTERNAL)
    [result] = _results(llm)
    [row] = json.loads(result.content)["popular"]
    assert "loans" not in row
    assert (row["copies"], row["on_loan"]) == (2, 2) and row["synced_at"].startswith("2026-11-18")


# --- 구매 요청서 초안 tool ---


async def test_draft_saves_pending_with_code_filled_items(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/admin] 구매 요청서 초안 tool / 초안 저장"""
    await _setup(session, library_a.id)
    llm = FakeLlm([candidates(), draft((VALID_ISBN, 1), (VALID_ISBN_2, 2)), answer()])
    await _run(session, llm, library_a.id)
    result = _results(llm, 2)[-1]
    assert not result.is_error, result.content
    body = json.loads(result.content)
    assert set(body) == {"purchase_request_id", "status", "item_count", "note"}
    assert (body["status"], body["item_count"]) == ("pending_approval", 2)
    request = await svc.get_request(session, library_a.id, body["purchase_request_id"])
    assert request.status == ApprovalStatus.PENDING_APPROVAL and request.created_by is None
    assert [(i.isbn, i.reason_kind.value, i.quantity, i.title) for i in request.items] == [
        (VALID_ISBN, "book_request", 1, "희망 책"),
        (VALID_ISBN_2, "popular", 2, "인기 책"),
    ]
    assert request.total_amount is None


async def test_draft_rejects_isbn_outside_candidates(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/admin] 구매 요청서 초안 tool / 후보에 없는 ISBN"""
    await _setup(session, library_a.id)
    llm = FakeLlm([candidates(), draft((VALID_ISBN, 1), (VALID_ISBN_3, 1)), answer("못 올렸어요")])
    await _run(session, llm, library_a.id)
    result = _results(llm, 2)[-1]
    assert result.is_error and VALID_ISBN_3 in result.content
    assert await svc.list_requests(session, library_a.id) == []


async def test_draft_prefers_book_request_when_in_both(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/admin] 구매 요청서 초안 tool / 두 후보에 모두 있는 ISBN

    사본이 분실돼 지금은 추천할 수 없지만(희망도서 후보에 남음) 대출 기록은 있는 책(인기 후보)이다.
    """
    member = await add_member(session, library_a.id, "M0001")
    await _popular_book(session, library_a.id, member, VALID_ISBN_2, status="lost")
    await add_book_request(session, library_a.id, member_id=member["id"], isbn=VALID_ISBN_2)
    llm = FakeLlm([candidates(), draft((VALID_ISBN_2, 1)), answer()])
    await _run(session, llm, library_a.id)
    listed = json.loads(_results(llm)[0].content)
    assert [w["isbn"] for w in listed["wishes"]] == [VALID_ISBN_2]
    assert [p["isbn"] for p in listed["popular"]] == [VALID_ISBN_2]
    [request] = await svc.list_requests(session, library_a.id)
    assert [i.reason_kind.value for i in request.items] == ["book_request"]


async def test_draft_records_only_items(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/admin] 구매 요청서 초안 tool / 초안 저장 (실행 기록에는 항목만)"""
    await _setup(session, library_a.id)
    llm = FakeLlm([candidates(), draft((VALID_ISBN, 1)), answer()])
    await _run(session, llm, library_a.id)
    [step] = await session.scalars(
        select(AgentStep).where(AgentStep.name == "draft_purchase_request")
    )
    assert set(step.detail) == {"items"}
    assert step.detail["items"] == [{"isbn": VALID_ISBN, "quantity": 1, "reason": "신청 2건"}]
    assert DRAFT_PURCHASE_REQUEST.record_fields == ("items",)


# --- 회원 값과 정가 조회 (API 경로 전체) ---


async def test_canary_requester_never_reaches_llm_or_records(
    admin_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/admin] 구매 요청서 tool의 회원 값 / 카나리아 신청 회원

    [agent/admin] 구매 요청서 초안 tool / 정가 조회 없음 (같은 실행에서 정가 조회기를 부르지 않는다)
    """
    await _setup(session, library_a.id)
    prices = FakeListPrices({VALID_ISBN: 15000, VALID_ISBN_2: 12000})
    app.dependency_overrides[get_list_prices] = lambda: prices
    fake_llm.script(candidates(), draft((VALID_ISBN, 1), (VALID_ISBN_2, 1)), answer())
    res = await admin_client.post(
        "/admin-agent/messages", json={"message": "희망도서랑 인기 책으로 구매 요청서 만들어 줘"}
    )
    assert res.status_code == 200
    assert [e.name for e in parse_sse(res.text)][-1] == "done"
    assert fake_llm.calls == 3
    assert prices.calls == []

    sent = repr(fake_llm.llm.requests)
    tables = (
        "agent_runs",
        "agent_steps",
        "chat_messages",
        "chat_sessions",
        "purchase_requests",
        "purchase_request_items",
    )
    dumped = []
    for table in tables:
        rows = await session.execute(text(f"SELECT row_to_json(t)::text FROM {table} t"))
        dumped.extend(r[0] for r in rows)
    stored = " ".join(dumped)
    assert VALID_ISBN in stored  # 요청서는 저장됐다
    for value in CANARY.values():
        assert value not in sent, value
        assert value not in stored, value

    # 같은 값이 관리자 희망도서 목록에는 나온다(검사가 헛돌지 않는지 확인).
    listed = await admin_client.get("/book-requests")
    assert CANARY["member_number"] in listed.text


# --- 결과 사건 ---


async def test_draft_result_event(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/admin] 초안 결과 사건 / 구매 요청서 초안"""
    await _setup(session, library_a.id)
    llm = FakeLlm([candidates(), draft((VALID_ISBN, 1)), answer()])
    events = await _run(session, llm, library_a.id)
    [value] = [e.value for e in events if isinstance(e, ResultEvent)]
    body = json.loads(_results(llm, 2)[-1].content)
    assert value.model_dump(mode="json") == {
        "kind": "draft",
        "draft": "purchase",
        "id": body["purchase_request_id"],
    }
