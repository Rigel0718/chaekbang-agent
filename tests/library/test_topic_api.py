"""[catalog/topic-recommendation] 주제로 찾기 API: `GET /catalog/topic`.

가짜 인코더로 돈다(임베딩 서버 없음). 순위 규칙 자체는 `test_topic_search.py`가 본다.
"""

from collections.abc import AsyncIterator, Sequence

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.embedding import EmbeddingError, EmbeddingFailure
from app.central.official_embeddings import run_official_embedding
from app.library.api.librarian import get_query_encoder
from app.library.recommendation.embeddings import run_library_embedding
from app.library.recommendation.search import search_collection
from app.library.services import topic as topic_service
from app.library.services.topic import TopicResult, search_by_topic, search_topic_text
from app.main import app
from tests.conftest import Tenant
from tests.embedding_helpers import FakeEmbedder, toward, unit
from tests.helpers import add_held_book


class FailingEmbedder(FakeEmbedder):
    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        self.query_calls.append(list(texts))
        raise EmbeddingError(EmbeddingFailure.UNREACHABLE, "연결 거부")


@pytest.fixture(autouse=True)
async def _no_encoder(_app: None) -> AsyncIterator[None]:
    """기본은 인코더 없음(임베딩 서버를 부르지 않는다). 쓰는 테스트가 덮어쓴다. `_app`이 치운다."""
    app.dependency_overrides[get_query_encoder] = lambda: None
    yield


def _use(encoder: FakeEmbedder | None) -> None:
    app.dependency_overrides[get_query_encoder] = lambda: encoder


async def _shelf(session: AsyncSession, library_id: int) -> None:
    """키워드가 맞는 책 둘과 낱말은 없지만 벡터가 가까운 책 하나."""
    await add_held_book(session, library_id, title="채식주의자", description="소설")
    await add_held_book(session, library_id, title="채식 식탁", description="요리")
    await add_held_book(session, library_id, title="고기 없는 날 가까운책")


def _embedder() -> FakeEmbedder:
    return FakeEmbedder(vectors={"가까운책": toward(0.95), "채식": unit(1)})


async def _load(session: AsyncSession, embedder: FakeEmbedder, library_id: int) -> None:
    await run_official_embedding(session, embedder, full=True)
    await run_library_embedding(session, embedder, full=True, library_id=library_id)


def _ids(items: list[dict]) -> list[int]:
    return [item["library_book_id"] for item in items]


async def test_topic_api_matches_product_path(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/topic-recommendation] 주제로 찾기 API / 제품 경로와 같은 결과"""
    await _shelf(session, library_a.id)
    embedder = _embedder()
    await _load(session, embedder, library_a.id)
    _use(embedder)
    response = await kiosk_client.get("/catalog/topic", params={"q": "채식 소설"})
    assert response.status_code == 200
    expected = await search_by_topic(session, library_a.id, ["채식", "소설"], encoder=embedder)
    assert _ids(response.json()) == [c.library_book.id for c in expected.candidates]
    assert response.json()
    item = response.json()[0]
    assert {"title", "available_count", "shelf_location", "cover_url"} <= set(item)
    assert "reason" not in item


async def test_topic_api_falls_back_when_encoder_fails(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/topic-recommendation] 주제로 찾기 API / 인코더가 실패함"""
    await _shelf(session, library_a.id)
    failing = FailingEmbedder()
    _use(failing)
    response = await kiosk_client.get("/catalog/topic", params={"q": "채식"})
    assert response.status_code == 200
    keyword = await search_collection(session, library_a.id, ["채식"])
    assert _ids(response.json()) == [c.library_book.id for c in keyword]
    assert failing.query_calls  # 인코딩을 시도했고 실패해서 내려갔다


@pytest.mark.parametrize("q", [" · ", "   ", "!?"])
async def test_topic_api_no_words_is_empty(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant, q: str
) -> None:
    """[catalog/topic-recommendation] 주제로 찾기 API / 낱말 없음"""
    await _shelf(session, library_a.id)
    embedder = _embedder()
    _use(embedder)
    response = await kiosk_client.get("/catalog/topic", params={"q": q})
    assert response.status_code == 200
    assert response.json() == []  # 둘러보기로 아무 책이나 나오지 않는다
    assert embedder.query_calls == []


async def test_topic_api_requires_token(client: AsyncClient) -> None:
    """[catalog/topic-recommendation] 주제로 찾기 API / 토큰 없음"""
    assert (await client.get("/catalog/topic", params={"q": "채식"})).status_code == 401


@pytest.mark.parametrize("q", ["", "가" * 101])
async def test_topic_api_rejects_bad_query(kiosk_client: AsyncClient, q: str) -> None:
    """[catalog/topic-recommendation] 주제로 찾기 API / 잘못된 질의"""
    assert (await kiosk_client.get("/catalog/topic", params={"q": q})).status_code == 422
    assert (await kiosk_client.get("/catalog/topic")).status_code == 422


async def test_topic_api_ignores_library_id_param(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/topic-recommendation] 주제로 찾기 API / 요청의 기관 값 무시"""
    mine = await add_held_book(session, library_a.id, title="공룡 백과")
    other = await add_held_book(session, library_b.id, title="공룡 도감")
    response = await kiosk_client.get(
        "/catalog/topic", params={"q": "공룡", "library_id": library_b.id}
    )
    assert response.status_code == 200
    assert _ids(response.json()) == [mine["id"]]
    assert other["id"] not in _ids(response.json())


async def test_topic_api_other_library_vectors_not_shown(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/topic-recommendation] 주제로 찾기 API / 요청의 기관 값 무시 (다른 기관 벡터)"""
    await add_held_book(session, library_a.id, title="우리 책 가까운책")
    other = await add_held_book(session, library_b.id, title="남의 책 가까운책")
    embedder = _embedder()
    await _load(session, embedder, library_a.id)
    await _load(session, embedder, library_b.id)
    _use(embedder)
    response = await kiosk_client.get("/catalog/topic", params={"q": "채식"})
    assert other["id"] not in _ids(response.json())


async def test_topic_api_leaves_no_records(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/topic-recommendation] 주제로 찾기 API는 기록을 남기지 않음 / 호출 후 기록"""
    await _shelf(session, library_a.id)

    async def counts() -> tuple[int, ...]:
        tables = ("agent_runs", "chat_messages", "recommendation_events")
        return tuple([await session.scalar(text(f"select count(*) from {t}")) for t in tables])

    before = await counts()
    await kiosk_client.get("/catalog/topic", params={"q": "채식"})
    assert await counts() == before


async def test_search_topic_text_splits_on_whitespace(
    session: AsyncSession, library_a: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[catalog/topic-recommendation] 주제로 찾기 API / 제품 경로와 같은 결과 (낱말 나누기)"""
    seen: list[list[str]] = []

    async def fake(session, library_id, keywords, *, encoder, within=None) -> TopicResult:
        seen.append(list(keywords))
        return TopicResult([], keyword_matched=False, vector_used=False)

    monkeypatch.setattr(topic_service, "search_by_topic", fake)
    await search_topic_text(session, library_a.id, "채식   소설\t이야기", encoder=None)
    assert seen == [["채식", "소설", "이야기"]]
    seen.clear()
    await search_topic_text(session, library_a.id, "채식 · C++", encoder=None)
    assert seen == [["채식", "C++"]]  # 글자·숫자 없는 낱말만 빼고 기호는 그대로 둔다
    seen.clear()
    await search_topic_text(session, library_a.id, " · ", encoder=None)
    assert seen == []  # 낱말이 없으면 제품 경로를 부르지 않는다
