"""[agent/librarian] 소장 도서 검색 tool: 주제로 찾기 결과의 모양과 표시, 질의 인코더 실행 값.

가짜 LLM과 가짜 인코더로 돈다. 순위와 내려가기의 계산은 `test_topic_search.py`가 본다.
"""

import json

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import ToolResult
from app.agent.models import AgentStep, StepKind
from app.central.official_embeddings import run_official_embedding
from app.library.api.librarian import get_query_encoder
from app.library.recommendation.embeddings import run_library_embedding
from app.library.recommendation.search import search_collection
from app.library.services.topic import QUERY_ENCODER, search_by_topic
from app.library.tools import NO_KEYWORD_MATCH, NO_SEARCH_RESULT
from app.main import app
from tests.agent.fakes import FakeLlm
from tests.conftest import Tenant
from tests.embedding_helpers import FakeEmbedder, toward, unit
from tests.library.chat_helpers import LlmSlot, event, talk
from tests.library.librarian_helpers import add_held_book, run_librarian, search, submit
from tests.library.test_topic_search import Failing


def _results(llm: FakeLlm, request: int = 1) -> list[dict]:
    messages = llm.requests[request]["messages"]
    return [json.loads(m.content) for m in messages if isinstance(m, ToolResult)]


async def _shelf(session: AsyncSession, library_id: int) -> FakeEmbedder:
    for title in ("공룡 대백과", "공룡 화석", "고생물 이야기 가까운책"):
        await add_held_book(session, library_id, title=title)
    embedder = FakeEmbedder(vectors={"가까운책": toward(0.95), "공룡": unit(1)})
    await run_official_embedding(session, embedder, full=True)
    await run_library_embedding(session, embedder, full=True, library_id=library_id)
    embedder.query_calls.clear()
    return embedder


async def test_ordinary_result(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/librarian] 소장 도서 검색 결과 / 보통 결과

    [agent/librarian] 조회 tool / 소장 도서 검색이 주제로 찾기를 씀
    """
    embedder = await _shelf(session, library_a.id)
    llm = FakeLlm([search("공룡"), submit("추천해요")])
    await run_librarian(session, llm, library_a.id, tool_values={QUERY_ENCODER: embedder})
    [result] = _results(llm)
    assert result["note"] is None
    expected = await search_by_topic(session, library_a.id, ["공룡"], encoder=embedder)
    ids = [c.library_book.id for c in expected.candidates]
    assert [b["library_book_id"] for b in result["books"]] == ids
    assert ["공룡"] in embedder.query_calls  # 벡터 질의는 낱말을 이은 것이다
    assert "available_count" in result["books"][0] and "ranks" not in result["books"][0]


async def test_empty_result(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/librarian] 소장 도서 검색 결과 / 빈 결과"""
    llm = FakeLlm([search("공룡"), submit("없어요", suggest=True)])
    await run_librarian(session, llm, library_a.id, tool_values={QUERY_ENCODER: FakeEmbedder()})
    assert _results(llm) == [{"books": [], "note": NO_SEARCH_RESULT}]


async def test_keyword_missing_note(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/librarian] 소장 도서 검색 결과 / 키워드 근거 없음"""
    embedder = await _shelf(session, library_a.id)
    llm = FakeLlm([search("없는낱말"), submit("없어요", suggest=True)])
    await run_librarian(session, llm, library_a.id, tool_values={QUERY_ENCODER: embedder})
    [result] = _results(llm)
    assert result["books"] and result["note"] == NO_KEYWORD_MATCH


async def test_fallback_has_same_shape(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/librarian] 소장 도서 검색 결과 / 내려간 결과의 모양"""
    await _shelf(session, library_a.id)
    llm = FakeLlm([search("공룡"), submit("추천해요")])
    await run_librarian(session, llm, library_a.id, tool_values={QUERY_ENCODER: Failing()})
    [result] = _results(llm)
    assert set(result) == {"books", "note"} and result["note"] is None
    keyword = await search_collection(session, library_a.id, ["공룡"])
    assert [b["library_book_id"] for b in result["books"]] == [c.library_book.id for c in keyword]
    assert "unreachable" not in json.dumps(result)


async def test_no_keywords_in_run_record(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/librarian] 소장 도서 검색 결과 / 실행 기록에 낱말 없음"""
    embedder = await _shelf(session, library_a.id)
    llm = FakeLlm([search("비밀낱말"), submit("없어요", suggest=True)])
    await run_librarian(session, llm, library_a.id, tool_values={QUERY_ENCODER: embedder})
    steps = list(
        await session.scalars(
            select(AgentStep).where(
                AgentStep.library_id == library_a.id, AgentStep.kind == StepKind.TOOL
            )
        )
    )
    assert [s.name for s in steps] == ["search_collection"]
    assert steps[0].detail is None


async def test_browse_without_keywords(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/librarian] 조회 tool / 낱말 없는 검색"""
    embedder = await _shelf(session, library_a.id)
    llm = FakeLlm([search(), submit("추천해요")])
    await run_librarian(session, llm, library_a.id, tool_values={QUERY_ENCODER: embedder})
    [result] = _results(llm)
    browse = await search_collection(session, library_a.id, [])
    assert [b["library_book_id"] for b in result["books"]] == [c.library_book.id for c in browse]
    assert embedder.query_calls == []


async def test_chat_passes_encoder(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/librarian] 질의 인코더 실행 값 / 인코더를 넘김"""
    embedder = await _shelf(session, library_a.id)
    app.dependency_overrides[get_query_encoder] = lambda: embedder
    fake_llm.script(search("공룡", "화석"), submit("이 책을 보세요"))
    events = await talk(kiosk_client, "공룡 화석 책 있어요?")
    assert event(events, "answer")["message"] == "이 책을 보세요"
    assert ["공룡 화석"] in embedder.query_calls


async def test_chat_without_encoder(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/librarian] 질의 인코더 실행 값 / 인코더 없음"""
    await _shelf(session, library_a.id)
    llm = fake_llm.script(search("공룡"), submit("이 책을 보세요"))
    events = await talk(kiosk_client, "공룡 책 있어요?")
    assert event(events, "answer")["message"] == "이 책을 보세요"
    [result] = _results(llm)
    keyword = await search_collection(session, library_a.id, ["공룡"])
    assert [b["library_book_id"] for b in result["books"]] == [c.library_book.id for c in keyword]
