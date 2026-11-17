"""[features/children] 어린이 도서 검색 tool이 주제로 찾기를 어린이 범위로 쓴다(가짜 인코더)."""

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import ToolResult
from app.central.official_embeddings import run_official_embedding
from app.features.children.service import children_book_ids
from app.features.children.tools import children_extension
from app.library.models.library import LoanMode
from app.library.recommendation.embeddings import run_library_embedding
from app.library.recommendation.search import search_collection
from app.library.services.topic import QUERY_ENCODER
from tests.agent.fakes import FakeLlm
from tests.conftest import Tenant
from tests.embedding_helpers import FakeEmbedder, toward, unit
from tests.helpers import add_audience
from tests.library.librarian_helpers import (
    add_held_book,
    librarian,
    run_librarian,
    search,
    submit,
)
from tests.library.test_topic_search import Failing


async def _shelf(session: AsyncSession, library_id: int) -> tuple[dict, list[int], FakeEmbedder]:
    """벡터 1위는 일반 도서이고, 어린이 도서 열두 권이 낱말 `공룡`에 맞는다."""
    general = await add_held_book(session, library_id, title="가까운책 일반서")
    kids = []
    for i in range(12):
        book = await add_held_book(session, library_id, title=f"공룡 그림책 {i:02d}")
        await add_audience(session, library_id, book["id"])
        kids.append(book["id"])
    embedder = FakeEmbedder(vectors={"가까운책": toward(0.99), "공룡": unit(1, 0.5)})
    await run_official_embedding(session, embedder, full=True)
    await run_library_embedding(session, embedder, full=True, library_id=library_id)
    return general, kids, embedder


async def _children_search(session, library_id: int, encoder) -> list[int]:
    llm = FakeLlm([search("공룡", name="search_children_books"), submit("없어요", suggest=True)])
    profile = librarian(LoanMode.INTERNAL, children_extension())
    await run_librarian(
        session, llm, library_id, "7살 공룡 책", prof=profile, tool_values={QUERY_ENCODER: encoder}
    )
    [result] = [m for m in llm.requests[1]["messages"] if isinstance(m, ToolResult)]
    return [row["library_book_id"] for row in json.loads(result.content)["books"]]


async def test_vector_top_general_book_left_out(session: AsyncSession, library_a: Tenant) -> None:
    """[features/children] 어린이 도서 검색 tool / 벡터 1위가 일반 도서"""
    general, kids, embedder = await _shelf(session, library_a.id)
    ids = await _children_search(session, library_a.id, embedder)
    assert general["id"] not in ids
    assert 0 < len(ids) <= 10 and set(ids) <= set(kids)
    assert ["공룡"] in embedder.query_calls


async def test_fallback_children_search(session: AsyncSession, library_a: Tenant) -> None:
    """[features/children] 어린이 도서 검색 tool / 내려간 어린이 검색"""
    _, _, _ = await _shelf(session, library_a.id)
    ids = await _children_search(session, library_a.id, Failing())
    keyword = await search_collection(
        session, library_a.id, ["공룡"], within=children_book_ids(library_a.id)
    )
    assert ids == [c.library_book.id for c in keyword]
