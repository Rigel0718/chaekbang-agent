"""[agent/admin] 큐레이션 초안 tool·소장 도서 검색, [agent/librarian] 큐레이션 tool (가짜 LLM)."""

import json
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import ToolResult
from app.agent.models import AgentStep
from app.agent.runner import AnswerEvent, ResultEvent, run
from app.features.children.analytics import admin_extension
from app.features.children.tools import children_extension
from app.library.admin_agent import build_admin_profiles
from app.library.api.librarian import get_query_encoder
from app.library.approval import ApprovalStatus
from app.library.curation_tools import DRAFT_CURATION, GET_CURATIONS, NO_CURATION
from app.library.models.library import LoanMode
from app.library.recommendation.search import search_collection
from app.library.schemas.curation import CurationWrite
from app.library.services import curations as svc
from app.main import app
from tests.agent.fakes import FakeLlm, call, tool_turn
from tests.conftest import Tenant
from tests.embedding_helpers import FakeEmbedder
from tests.helpers import add_audience, add_held_book
from tests.library.chat_helpers import LlmSlot, parse_sse
from tests.library.librarian_helpers import call as lcall
from tests.library.librarian_helpers import librarian, run_librarian, submit, turn


def _results(llm: FakeLlm, request: int = 1) -> list[Any]:
    messages = llm.requests[request]["messages"]
    return [m for m in messages if isinstance(m, ToolResult)]


def draft(ids: list[int], title: str = "공룡 특집", reason: str = "공룡이 나와요") -> Any:
    return tool_turn(
        call(
            "draft_curation",
            {
                "title": title,
                "intro": "공룡 좋아하는 친구들에게",
                "library_book_ids": ids,
                "reasons": [reason] * len(ids),
            },
        )
    )


def answer(message: str = "승인 대기로 올렸어요.", unsupported: str | None = None) -> Any:
    return tool_turn(
        call("submit_answer", {"message": message, "unsupported": unsupported}, "answer")
    )


def admin(loan_mode: LoanMode = LoanMode.INTERNAL):
    return build_admin_profiles([admin_extension()])[loan_mode]


async def _run_admin(session: AsyncSession, llm: FakeLlm, library_id: int, **values: Any):
    return [
        e
        async for e in run(
            session=session,
            llm=llm,
            profile=admin(),
            library_id=library_id,
            user_text="공룡 책으로 큐레이션 만들어 줘",
            **values,
        )
    ]


async def _books(
    session: AsyncSession, library_id: int, n: int = 3, title: str = "공룡"
) -> list[int]:
    return [
        (await add_held_book(session, library_id, title=f"{title} {i}"))["id"] for i in range(n)
    ]


# --- 큐레이션 초안 tool ---


async def test_draft_saves_pending(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/admin] 큐레이션 초안 tool / 초안 저장"""
    ids = await _books(session, library_a.id)
    llm = FakeLlm([draft(ids), answer()])
    await _run_admin(session, llm, library_a.id)
    [result] = _results(llm)
    body = json.loads(result.content)
    assert not result.is_error
    assert body["status"] == "pending_approval"
    assert body["book_count"] == 3
    curation = await svc.get_curation(session, library_a.id, body["curation_id"])
    assert curation.status == ApprovalStatus.PENDING_APPROVAL
    assert curation.created_by is None
    assert [i.library_book_id for i in curation.items] == ids


async def test_draft_rejects_unrecommendable(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/admin] 큐레이션 초안 tool / 추천할 수 없는 책"""
    ids = await _books(session, library_a.id, 2)
    withdrawn = (await add_held_book(session, library_a.id, "withdrawn", title="공룡 제적"))["id"]
    llm = FakeLlm([draft([*ids, withdrawn]), answer("못 올렸어요")])
    events = await _run_admin(session, llm, library_a.id)
    [result] = _results(llm)
    assert result.is_error
    assert str(withdrawn) in result.content
    assert await svc.list_curations(session, library_a.id) == []
    assert any(isinstance(e, AnswerEvent) for e in events)


async def test_draft_content_rules_are_domain_errors(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/admin] 큐레이션 초안 tool: 내용 규칙 위반과 개수 불일치는 LLM이 받는 오류다"""
    ids = await _books(session, library_a.id)
    mismatch = tool_turn(
        call(
            "draft_curation",
            {"title": "t", "intro": None, "library_book_ids": ids, "reasons": ["하나"]},
        )
    )
    llm = FakeLlm([draft(ids[:2]), mismatch, answer()])
    await _run_admin(session, llm, library_a.id)
    errors = [r for r in _results(llm, 2) if r.is_error]
    assert len(errors) == 2
    assert await svc.list_curations(session, library_a.id) == []


async def test_draft_records_only_book_ids(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/admin] 큐레이션 초안 tool / 실행 기록"""
    ids = await _books(session, library_a.id)
    llm = FakeLlm([draft(ids, title="비밀제목XYZ", reason="비밀이유QWE"), answer()])
    await _run_admin(session, llm, library_a.id)
    [step] = await session.scalars(select(AgentStep).where(AgentStep.name == "draft_curation"))
    assert step.detail == {"library_book_ids": ids}
    runs = await session.execute(text("SELECT row_to_json(r)::text FROM agent_runs r"))
    steps = await session.execute(text("SELECT row_to_json(s)::text FROM agent_steps s"))
    dumped = " ".join(r[0] for r in [*runs, *steps])
    for secret in ("비밀제목XYZ", "비밀이유QWE", "공룡 좋아하는 친구들에게"):
        assert secret not in dumped
    assert DRAFT_CURATION.record_fields == ("library_book_ids",)


# --- 운영 에이전트의 소장 도서 검색 ---


async def test_admin_search_without_encoder(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/admin] 운영 에이전트의 소장 도서 검색 / 인코더 없이 검색"""
    await _books(session, library_a.id)
    llm = FakeLlm([turn(lcall("search_collection", {"keywords": ["공룡"]})), answer()])
    await _run_admin(session, llm, library_a.id)
    [result] = _results(llm)
    keyword = await search_collection(session, library_a.id, ["공룡"])
    books = json.loads(result.content)["books"]
    assert [b["library_book_id"] for b in books] == [c.library_book.id for c in keyword]


async def test_admin_chat_passes_encoder(
    admin_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/admin] 운영 에이전트의 소장 도서 검색: 대화 코드가 질의 인코더를 넘긴다"""
    await _books(session, library_a.id)
    embedder = FakeEmbedder()
    app.dependency_overrides[get_query_encoder] = lambda: embedder
    fake_llm.script(
        turn(lcall("search_collection", {"keywords": ["공룡", "화석"]})), answer("찾았어요")
    )
    res = await admin_client.post("/admin-agent/messages", json={"message": "공룡 책 찾아 줘"})
    assert res.status_code == 200
    assert [e.name for e in parse_sse(res.text)][-1] == "done"
    assert ["공룡 화석"] in embedder.query_calls


# --- AI 사서 큐레이션 tool ---


async def _publish(
    session: AsyncSession, tenant: Tenant, ids: list[int], title: str = "이달의 추천"
):
    data = CurationWrite(
        title=title, items=[{"library_book_id": i, "reason": f"이유 {i}"} for i in ids]
    )
    curation = await svc.create_curation(session, tenant.id, None, data, submit=True)
    return await svc.approve_curation(session, tenant.id, curation.id, tenant.admin["id"])


def _curations_call() -> Any:
    return turn(lcall("get_curations", {}))


async def test_get_curations_published_only(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/librarian] 큐레이션 tool / 게시본만"""
    ids = await _books(session, library_a.id)
    await svc.create_curation(
        session,
        library_a.id,
        None,
        CurationWrite(title="대기", items=[{"library_book_id": i, "reason": "r"} for i in ids]),
        submit=True,
    )
    await _publish(session, library_a, ids)
    llm = FakeLlm([_curations_call(), submit("추천 목록이에요", ids[0])])
    await run_librarian(session, llm, library_a.id, "이달의 추천 뭐 있어?")
    [result] = _results(llm)
    body = json.loads(result.content)
    assert [c["title"] for c in body["curations"]] == ["이달의 추천"]
    assert body["note"] is None
    book = body["curations"][0]["books"][0]
    assert book["library_book_id"] == ids[0]
    assert book["reason"] == f"이유 {ids[0]}"
    assert "available_count" in book


async def test_get_curations_empty(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/librarian] 큐레이션 tool / 게시본 없음"""
    llm = FakeLlm([_curations_call(), submit("없어요")])
    await run_librarian(session, llm, library_a.id, "이달의 추천 뭐 있어?")
    [result] = _results(llm)
    assert json.loads(result.content) == {"curations": [], "note": NO_CURATION}


async def test_get_curations_other_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[agent/librarian] 큐레이션 tool / 다른 기관의 게시본"""
    await _publish(session, library_b, await _books(session, library_b.id))
    llm = FakeLlm([_curations_call(), submit("없어요")])
    await run_librarian(session, llm, library_a.id, "이달의 추천 뭐 있어?")
    [result] = _results(llm)
    assert json.loads(result.content)["curations"] == []


async def test_get_curations_children_check(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/librarian] 큐레이션 tool / 어린이 요청의 큐레이션 책"""
    kids = await _books(session, library_a.id, 2, "어린이 공룡")
    for i in kids:
        await add_audience(session, library_a.id, i)
    general = (await add_held_book(session, library_a.id, title="어른 공룡"))["id"]
    await _publish(session, library_a, [*kids, general])
    prof = librarian(LoanMode.INTERNAL, children_extension())
    llm = FakeLlm(
        [
            _curations_call(),
            submit("추천해요", kids[0], general),
            submit("추천해요", kids[0], general),
            submit("추천해요", kids[0], general),
            submit("추천해요", kids[0], general),
        ]
    )
    events = await run_librarian(
        session, llm, library_a.id, "초등학생 아이가 볼 책 추천해줘", prof=prof
    )
    [final] = [e for e in events if isinstance(e, AnswerEvent)]
    shown = [r.library_book_id for r in final.answer.recommendations]
    assert general not in shown
    assert kids[0] in shown


def test_profiles_have_curation_tool() -> None:
    """[agent/librarian] 큐레이션 tool: 두 운영 방식의 프로필 모두 가진다"""
    for mode in LoanMode:
        assert GET_CURATIONS in librarian(mode).tools


# --- 결과 사건 ---


async def test_draft_result_event(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/admin] 초안 결과 사건 / 큐레이션 초안"""
    ids = await _books(session, library_a.id)
    llm = FakeLlm([draft(ids), answer()])
    events = await _run_admin(session, llm, library_a.id)
    [value] = [e.value for e in events if isinstance(e, ResultEvent)]
    body = json.loads(_results(llm)[0].content)
    assert value.model_dump(mode="json") == {
        "kind": "draft",
        "draft": "curation",
        "id": body["curation_id"],
    }


async def test_failed_draft_has_no_result_event(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/admin] 초안 결과 사건 / 초안이 저장되지 않음"""
    ids = await _books(session, library_a.id, 2)
    llm = FakeLlm([draft(ids), answer("못 올렸어요")])
    events = await _run_admin(session, llm, library_a.id)
    assert _results(llm)[0].is_error
    assert not any(isinstance(e, ResultEvent) for e in events)
