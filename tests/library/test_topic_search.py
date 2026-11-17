"""[catalog/topic-recommendation] 제품 경로의 주제로 찾기: 기본 설정, 내려가기, 키워드 근거, 범위.

가짜 인코더로 돈다. 질의 인코더의 시간 제한·쉬기는 `tests/external/test_guarded_embedder.py`.
"""

import logging
from collections.abc import Sequence
from dataclasses import replace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.embedding import EmbeddingError, EmbeddingFailure, GuardedEmbedder
from app.central.official_embeddings import run_official_embedding
from app.features.children.service import children_book_ids
from app.library.recommendation.embeddings import run_library_embedding
from app.library.recommendation.search import search_collection
from app.library.recommendation.topic import TopicSettings, find_by_topic
from app.library.services.topic import search_by_topic
from tests.conftest import Tenant
from tests.embedding_helpers import FakeEmbedder, toward, unit
from tests.helpers import add_audience, add_held_book


class Failing(FakeEmbedder):
    def __init__(self, failure: EmbeddingFailure = EmbeddingFailure.UNREACHABLE, **kw) -> None:
        super().__init__(**kw)
        self.failure_kind = failure

    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        self.query_calls.append(list(texts))
        raise EmbeddingError(self.failure_kind, "연결 거부")


async def _load(session: AsyncSession, embedder: FakeEmbedder, library_id: int) -> None:
    await run_official_embedding(session, embedder, full=True)
    await run_library_embedding(session, embedder, full=True, library_id=library_id)


def _embedder(cosines: dict[str, float]) -> FakeEmbedder:
    """서명의 낱말마다 질의 `공룡`과의 유사도를 정한다(벡터 질의는 낱말을 이은 것).

    앞의 낱말이 먼저 맞으므로 정한 낱말이 `공룡`보다 앞선다. `공룡`만 든 서명은 질의와 같은 벡터다.
    """
    return FakeEmbedder(vectors={**{w: toward(c) for w, c in cosines.items()}, "공룡": unit(1)})


async def _shelf(session: AsyncSession, library_id: int) -> dict[str, dict]:
    """키워드 `공룡`이 맞는 책 셋과 맞지 않지만 벡터가 가까운 책 하나."""
    books = {}
    for name, description in (("공룡 대백과", "공룡"), ("공룡 화석", None), ("작은 공룡", None)):
        books[name] = await add_held_book(
            session, library_id, title=f"{name} 책", description=description
        )
    books["고생물"] = await add_held_book(session, library_id, title="고생물 이야기 가까운책")
    return books


def _ids(result) -> list[int]:
    return [c.library_book.id for c in result.candidates]


async def test_same_order_as_default_settings(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/topic-recommendation] 제품 경로의 주제로 찾기 / 기본 설정과 같은 순서"""
    await _shelf(session, library_a.id)
    embedder = _embedder({"가까운책": 0.95, "화석": 0.5})
    await _load(session, embedder, library_a.id)
    result = await search_by_topic(session, library_a.id, ["공룡"], encoder=embedder)
    expected = await find_by_topic(
        session, embedder, library_id=library_a.id, text="", keywords=["공룡"],
        settings=replace(TopicSettings(), limit=10),
    )  # fmt: skip
    assert _ids(result) == [item.library_book_id for item in expected]
    assert result.vector_used and result.keyword_matched and not result.keyword_missing


async def test_no_keywords_is_browse(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/topic-recommendation] 제품 경로의 주제로 찾기 / 낱말 없음"""
    await _shelf(session, library_a.id)
    embedder = FakeEmbedder()
    result = await search_by_topic(session, library_a.id, [" "], encoder=embedder)
    browse = await search_collection(session, library_a.id, [])
    assert _ids(result) == [c.library_book.id for c in browse]
    assert embedder.query_calls == [] and not result.keyword_missing


async def test_result_count(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/topic-recommendation] 제품 경로의 주제로 찾기 / 결과 수"""
    for i in range(30):
        await add_held_book(session, library_a.id, title=f"공룡 {i:02d}")
    embedder = FakeEmbedder()
    await _load(session, embedder, library_a.id)
    result = await search_by_topic(session, library_a.id, ["공룡"], encoder=embedder)
    assert len(result.candidates) == 10


@pytest.mark.parametrize(
    "failure",
    [EmbeddingFailure.UNREACHABLE, EmbeddingFailure.TIMEOUT, EmbeddingFailure.MODEL_MISMATCH],
)
async def test_falls_back_to_keyword_order(
    session: AsyncSession,
    library_a: Tenant,
    failure: EmbeddingFailure,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[catalog/topic-recommendation] 키워드 순위로 내려가기 / 서버가 꺼짐·시간 제한·다른 모델·로그

    테스트가 마이그레이션을 돌릴 때 Alembic의 `fileConfig`가 이미 있는 로거를 끄므로 다시 켠다.
    """
    monkeypatch.setattr(logging.getLogger("app.library.services.topic"), "disabled", False)
    await _shelf(session, library_a.id)
    await _load(session, FakeEmbedder(), library_a.id)
    with caplog.at_level(logging.WARNING, logger="app.library.services.topic"):
        result = await search_by_topic(
            session, library_a.id, ["공룡", "비밀낱말"], encoder=Failing(failure)
        )
    keyword = await search_collection(session, library_a.id, ["공룡", "비밀낱말"])
    assert _ids(result) == [c.library_book.id for c in keyword]
    assert not result.vector_used
    assert failure.value in caplog.text and "비밀낱말" not in caplog.text


async def test_no_encoder_is_keyword_order(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/topic-recommendation] 키워드 순위로 내려가기 (인코더 없음)"""
    await _shelf(session, library_a.id)
    result = await search_by_topic(session, library_a.id, ["공룡"], encoder=None)
    keyword = await search_collection(session, library_a.id, ["공룡"])
    assert _ids(result) == [c.library_book.id for c in keyword]


async def test_timeout_through_guarded_encoder(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/topic-recommendation] 키워드 순위로 내려가기 / 시간 제한 (질의 인코더를 거쳐)"""
    import asyncio

    class Slow(FakeEmbedder):
        async def encode_queries(self, texts):
            await asyncio.sleep(0.2)
            return await super().encode_queries(texts)

    await _shelf(session, library_a.id)
    guarded = GuardedEmbedder(Slow(), timeout=0.05, pause=30)
    result = await search_by_topic(session, library_a.id, ["공룡"], encoder=guarded)
    keyword = await search_collection(session, library_a.id, ["공룡"])
    assert _ids(result) == [c.library_book.id for c in keyword]
    assert guarded.last_failure is EmbeddingFailure.TIMEOUT


async def test_keyword_missing_marker(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/topic-recommendation] 키워드 근거 없음 표시 / 낱말이 맞는 책 없음"""
    await _shelf(session, library_a.id)
    embedder = _embedder({"가까운책": 0.95})
    await _load(session, embedder, library_a.id)
    missing = await search_by_topic(session, library_a.id, ["없는낱말"], encoder=embedder)
    assert missing.candidates and missing.keyword_missing


async def test_keyword_match_has_no_marker(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/topic-recommendation] 키워드 근거 없음 표시 / 낱말이 맞는 책 있음"""
    books = await _shelf(session, library_a.id)
    embedder = _embedder({"가까운책": 0.95})
    await _load(session, embedder, library_a.id)
    one = await search_by_topic(session, library_a.id, ["고생물"], encoder=embedder)
    assert books["고생물"]["id"] in _ids(one) and not one.keyword_missing


async def test_fallback_without_match_has_no_marker(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/topic-recommendation] 키워드 근거 없음 표시 / 내려간 결과"""
    await _shelf(session, library_a.id)
    result = await search_by_topic(session, library_a.id, ["없는낱말"], encoder=Failing())
    assert result.candidates == [] and not result.keyword_missing


async def test_other_library_vector_top(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/topic-recommendation] 제품 경로의 범위 / 다른 기관의 벡터 1위"""
    await _shelf(session, library_a.id)
    theirs = await add_held_book(session, library_b.id, title="남의 책 가까운책")
    embedder = _embedder({"가까운책": 0.99})
    await _load(session, embedder, library_a.id)
    await _load(session, embedder, library_b.id)
    result = await search_by_topic(session, library_a.id, ["공룡"], encoder=embedder)
    assert theirs["id"] not in _ids(result)


async def test_condition_before_vector(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/topic-recommendation] 제품 경로의 범위 / 조건 밖의 벡터 1위"""
    general = await add_held_book(session, library_a.id, title="공룡 일반서 가까운책")
    kids = []
    for name in ("그림책 하나 아이책", "그림책 둘 아이책"):
        book = await add_held_book(session, library_a.id, title=name)
        await add_audience(session, library_a.id, book["id"])
        kids.append(book["id"])
    embedder = _embedder({"가까운책": 0.99, "아이책": 0.3})
    await _load(session, embedder, library_a.id)
    unscoped = await search_by_topic(session, library_a.id, ["공룡"], encoder=embedder)
    assert _ids(unscoped)[0] == general["id"]
    result = await search_by_topic(
        session, library_a.id, ["공룡"], encoder=embedder, within=children_book_ids(library_a.id)
    )
    assert general["id"] not in _ids(result) and set(_ids(result)) == set(kids)
