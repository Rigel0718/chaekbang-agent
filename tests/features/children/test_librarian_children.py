"""[features/children] AI 사서의 어린이 도서 검색 tool과 어린이 최종 검사. 가짜 LLM만 쓴다."""

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import AssistantMessage, ToolResult, UserMessage
from app.agent.models import RunStatus
from app.features.children.tools import children_extension
from app.library.librarian import REPAIRED_MESSAGE
from app.library.models.library import LoanMode
from app.library.recommendation.cards import build_cards
from tests.agent.fakes import FakeLlm, answers, done
from tests.conftest import Tenant
from tests.helpers import add_audience
from tests.library.librarian_helpers import (
    add_held_book,
    librarian,
    run_librarian,
    search,
    submit,
)


def _profile():
    return librarian(LoanMode.INTERNAL, children_extension())


def _results(llm: FakeLlm, request: int) -> list[ToolResult]:
    return [m for m in llm.requests[request]["messages"] if isinstance(m, ToolResult)]


async def _books(session: AsyncSession, library_id: int):
    kids = await add_held_book(session, library_id, title="공룡 그림책")
    await add_audience(session, library_id, kids["id"], "children")
    general = await add_held_book(session, library_id, title="공룡 대백과")
    return kids, general


# --- 어린이 도서 검색 tool ---


async def test_children_tool_only_children(session: AsyncSession, library_a: Tenant) -> None:
    """[features/children] 어린이 도서 검색 tool / 어린이 도서만 나옴"""
    kids, general = await _books(session, library_a.id)
    marked_general = await add_held_book(session, library_a.id, title="공룡 화석")
    await add_audience(session, library_a.id, marked_general["id"], "general")
    llm = FakeLlm([search("공룡", name="search_children_books"), submit("추천", kids["id"])])
    await run_librarian(session, llm, library_a.id, "공룡 책", prof=_profile())
    [result] = _results(llm, 1)
    ids = [row["library_book_id"] for row in json.loads(result.content)]
    assert ids == [kids["id"]]


async def test_children_tool_other_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[features/children] 어린이 도서 검색 tool / 다른 기관의 어린이 구분"""
    ours = await add_held_book(session, library_a.id, title="공룡 그림책")
    theirs = await add_held_book(session, library_b.id, title="공룡 그림책")
    await add_audience(session, library_b.id, theirs["id"], "children")
    llm = FakeLlm([search("공룡", name="search_children_books"), submit("없어요", suggest=True)])
    await run_librarian(session, llm, library_a.id, "공룡 책", prof=_profile())
    [result] = _results(llm, 1)
    assert json.loads(result.content) == []
    assert ours["id"] != theirs["id"]


# --- 어린이 최종 검사 ---


async def test_children_request_general_book(session: AsyncSession, library_a: Tenant) -> None:
    """[features/children] 어린이 최종 검사 / 어린이 요청에 일반 도서"""
    kids, general = await _books(session, library_a.id)
    llm = FakeLlm([submit("둘 다요", kids["id"], general["id"]), submit("이 책요", kids["id"])])
    events = await run_librarian(session, llm, library_a.id, "7살 공룡 책", prof=_profile())
    [result] = _results(llm, 1)
    assert result.is_error
    assert str(general["id"]) in result.content
    [answer] = answers(events)
    assert [r.library_book_id for r in answer.recommendations] == [kids["id"]]


async def test_children_request_unclassified(session: AsyncSession, library_a: Tenant) -> None:
    """[features/children] 어린이 최종 검사 / 분류 없는 책"""
    unclassified = await add_held_book(session, library_a.id, title="공룡 이야기")
    llm = FakeLlm([submit("이 책요", unclassified["id"]), submit("없어요", suggest=True)])
    events = await run_librarian(session, llm, library_a.id, "7살 공룡 책", prof=_profile())
    assert _results(llm, 1)[-1].is_error
    assert answers(events)[0].recommendations == []


async def test_not_children_request(session: AsyncSession, library_a: Tenant) -> None:
    """[features/children] 어린이 최종 검사 / 어린이 요청이 아님"""
    _, general = await _books(session, library_a.id)
    llm = FakeLlm([submit("이 책요", general["id"])])
    events = await run_librarian(session, llm, library_a.id, "공룡 책 추천해줘", prof=_profile())
    assert done(events).status == RunStatus.COMPLETED
    assert answers(events)[0].recommendations[0].library_book_id == general["id"]


async def test_children_tool_marks_request(session: AsyncSession, library_a: Tenant) -> None:
    """[features/children] 어린이 요청 판단 / LLM이 어린이 tool을 씀"""
    kids, general = await _books(session, library_a.id)
    llm = FakeLlm(
        [
            search("공룡", name="search_children_books"),
            submit("이 책요", general["id"]),
            submit("이 책요", kids["id"]),
        ]
    )
    events = await run_librarian(session, llm, library_a.id, "공룡 책", prof=_profile())
    assert _results(llm, 2)[-1].is_error
    assert answers(events)[0].recommendations[0].library_book_id == kids["id"]


async def test_children_request_kept_in_history(session: AsyncSession, library_a: Tenant) -> None:
    """[features/children] 대화 안에서 유지 / 이어지는 질문 (검사에 반영)"""
    _, general = await _books(session, library_a.id)
    llm = FakeLlm([submit("이 책요", general["id"]), submit("없어요", suggest=True)])
    await run_librarian(
        session,
        llm,
        library_a.id,
        "다른 건요?",
        prof=_profile(),
        history=[UserMessage("7살 책"), AssistantMessage("추천했어요")],
    )
    assert _results(llm, 1)[-1].is_error


async def test_children_repeated_violation(session: AsyncSession, library_a: Tenant) -> None:
    """[features/children] 어린이 최종 검사 / 재시도 뒤에도 위반"""
    kids, general = await _books(session, library_a.id)
    bad = submit("둘 다요", general["id"], kids["id"])
    events = await run_librarian(
        session, FakeLlm([bad, bad, bad]), library_a.id, "7살 공룡 책", prof=_profile()
    )
    [answer] = answers(events)
    assert done(events).status == RunStatus.REPAIRED
    assert answer.message == REPAIRED_MESSAGE
    cards = await build_cards(session, library_a.id, answer)
    assert [c.library_book_id for c in cards] == [kids["id"]]
