"""[agent/librarian] 관련 책 tool (가짜 LLM)."""

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import ToolResult
from app.agent.models import AgentStep
from app.agent.tools import ToolContext
from app.library.models.catalog import LibraryBook
from app.library.services.related import SESSION_BOOKS, similar_for_book
from app.library.tools import NO_RELATED, related_tool
from tests.agent.fakes import FakeLlm, done
from tests.conftest import Tenant
from tests.library.librarian_helpers import call, run_librarian, submit, turn
from tests.library.test_related_books import _product_books, no_scopes  # noqa: F401
from tests.library.test_related_recommendation import _loaned, unlinked


def related(library_book_id: int | None, name: str = "find_related_books"):
    return turn(call(name, {"library_book_id": library_book_id}))


def _result(llm: FakeLlm) -> ToolResult:
    [result] = [m for m in llm.requests[1]["messages"] if isinstance(m, ToolResult)]
    return result


async def test_by_book_id(session: AsyncSession, library_a: Tenant, no_scopes) -> None:  # noqa: F811
    """[agent/librarian] 관련 책 tool / 책 id로 부름"""
    ids = await _product_books(session, library_a.id)
    llm = FakeLlm([related(ids["base"]), submit("있어요.")])
    await run_librarian(session, llm, library_a.id, "비슷한 거 있어요?")
    result = _result(llm)
    assert not result.is_error
    body = json.loads(result.content)
    expected = await similar_for_book(session, library_a.id, ids["base"])
    assert [b["library_book_id"] for b in body["books"]] == [
        i.candidate.library_book.id for i in expected
    ]
    assert all(b["basis_text"] for b in body["books"])
    assert {"shelf_location", "call_number", "description"} <= set(body["books"][0])
    assert body["note"] is None


async def test_book_of_other_library(
    session: AsyncSession,
    library_a: Tenant,
    library_b: Tenant,
    no_scopes,  # noqa: F811
) -> None:
    """[agent/librarian] 관련 책 tool / 다른 기관의 책 id"""
    other = await unlinked(session, library_b.id, "남의 책")
    llm = FakeLlm([related(other), submit("없어요.", suggest=True)])
    await run_librarian(session, llm, library_a.id)
    result = _result(llm)
    assert result.is_error
    assert "찾을 수 없어요." in result.content


async def test_empty_input_uses_session_books(
    session: AsyncSession,
    library_a: Tenant,
    no_scopes,  # noqa: F811
) -> None:
    """[agent/librarian] 관련 책 tool / 비워서 부름"""
    ids = await _product_books(session, library_a.id)
    llm = FakeLlm([related(None), submit("있어요.")])
    await run_librarian(
        session, llm, library_a.id, "더 없어요?", tool_values={SESSION_BOOKS: (ids["near"],)}
    )
    body = json.loads(_result(llm).content)
    found = [b["library_book_id"] for b in body["books"]]
    assert found and ids["near"] not in found
    assert all(t.startswith("최근 본 책과") for b in body["books"] for t in b["basis_text"])


async def test_no_session_books_uses_popular(
    session: AsyncSession,
    library_a: Tenant,
    no_scopes,  # noqa: F811
) -> None:
    """[agent/librarian] 관련 책 tool / 세션에 책이 없음"""
    busy = await _loaned(session, library_a.id, "많이 빌린 책", [1, 2, 3])
    quiet = await _loaned(session, library_a.id, "한 번 빌린 책", [4])
    llm = FakeLlm([related(None), submit("있어요.")])
    await run_librarian(session, llm, library_a.id, "아무거나 추천해 줘")
    body = json.loads(_result(llm).content)
    assert [b["library_book_id"] for b in body["books"]] == [busy, quiet]
    assert body["books"][0]["basis_text"] == ["우리 도서관에서 많이 빌린 책"]


async def test_empty_result_note(
    session: AsyncSession,
    library_a: Tenant,
    no_scopes,  # noqa: F811
) -> None:
    """[agent/librarian] 관련 책 tool / 빈 결과의 표시"""
    await unlinked(session, library_a.id, "아무도 안 빌린 책")
    llm = FakeLlm([related(None), submit("없어요.", suggest=True)])
    await run_librarian(session, llm, library_a.id, "아무거나 추천해 줘")
    assert json.loads(_result(llm).content) == {"books": [], "note": NO_RELATED}


async def test_recorded_input(session: AsyncSession, library_a: Tenant, no_scopes) -> None:  # noqa: F811
    """[agent/librarian] 관련 책 tool / 실행 기록의 입력"""
    ids = await _product_books(session, library_a.id)
    llm = FakeLlm([related(ids["base"]), submit("있어요.")])
    events = await run_librarian(
        session, llm, library_a.id, "비슷한 거", tool_values={SESSION_BOOKS: (ids["far"],)}
    )
    details = await session.scalars(
        select(AgentStep.detail).where(
            AgentStep.run_id == done(events).run_id, AgentStep.name == "find_related_books"
        )
    )
    assert list(details) == [{"library_book_id": ids["base"]}]


async def test_scope_of_factory(session: AsyncSession, library_a: Tenant, no_scopes) -> None:  # noqa: F811
    """[agent/librarian] 관련 책 tool / factory의 범위(보조)"""
    ids = await _product_books(session, library_a.id)
    tool = related_tool(
        "narrow",
        "좁힌 관련 책",
        "찾고 있어요",
        within=lambda library_id: select(LibraryBook.id).where(LibraryBook.id == ids["near"]),
    )
    data = tool.input_model(library_book_id=ids["base"])
    out = await tool.handler(ToolContext(library_a.id, session), data)
    assert [b["library_book_id"] for b in out["books"]] == [ids["near"]]
