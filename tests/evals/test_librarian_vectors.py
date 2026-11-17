"""[agent/librarian] AI 사서 평가 표본의 벡터 적재와 캐시. 가짜 인코더로 돈다(임베딩 서버 없음)."""

from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.models import OfficialBookEmbedding
from app.library.models.embedding import BookEmbedding
from evals.librarian.__main__ import vector_line
from evals.librarian.catalog import Sample, load_catalog, load_vectors
from evals.recommendation.cache import CachedEmbedder
from tests.embedding_helpers import FakeEmbedder
from tests.helpers import make_isbn


def _sample() -> Sample:
    books = [
        {
            "isbn13": make_isbn(900 + i)
            if i % 4
            else f"8800000000{i:03d}",  # 넷 중 하나는 ISBN 없음
            "title": f"평가 표본 {i}",
            "author": "표본 저자",
            "description": f"표본 소개 {i}",
        }
        for i in range(12)
    ]
    return Sample("2026-11-17", books)


async def _count(session: AsyncSession, model, **where) -> int:
    query = select(func.count()).select_from(model)
    for column, value in where.items():
        query = query.where(getattr(model, column) == value)
    return await session.scalar(query) or 0


async def test_sample_loads_vectors_and_reuses_cache(session: AsyncSession, tmp_path: Path) -> None:
    """[agent/librarian] 주제 요청에 답함 (평가 표본의 벡터 적재, 캐시가 차면 인코더를 안 부름)"""
    inner = FakeEmbedder()
    cached = CachedEmbedder(inner, tmp_path / "queries.json", tmp_path / "docs.json")
    catalog = await load_catalog(session, _sample(), embedder=cached)
    official = await _count(session, OfficialBookEmbedding)
    own = await _count(session, BookEmbedding, library_id=catalog.library_id)
    assert official > 0 and own > 0
    assert catalog.vectors == official + own == cached.encoded_documents
    assert (tmp_path / "docs.json").exists()

    again = FakeEmbedder()
    second = CachedEmbedder(again, tmp_path / "queries.json", tmp_path / "docs.json")
    assert await load_vectors(session, second, catalog.library_id) == catalog.vectors
    assert again.document_calls == [] and second.encoded_documents == 0
    assert second.cached_documents == catalog.vectors
    assert "새로 인코딩 0" in vector_line(second, catalog.vectors)


async def test_sample_without_vectors(session: AsyncSession) -> None:
    """[agent/librarian] 주제 요청에 답함 (--no-vectors: 벡터 없이 적재)"""
    catalog = await load_catalog(session, _sample())
    assert catalog.vectors == 0
    assert await _count(session, BookEmbedding, library_id=catalog.library_id) == 0
    assert vector_line(None, 0) == "벡터: 넣지 않음(--no-vectors)"


async def test_query_cache_checks_model_once(tmp_path: Path) -> None:
    """[agent/librarian] 주제 요청에 답함 (평가 질의 캐시: 없는 질의만 인코딩, 모델 확인 한 번)"""
    calls: list[str] = []

    class Counting(FakeEmbedder):
        async def check(self) -> None:
            calls.append("check")

    inner = Counting()
    cached = CachedEmbedder(inner, tmp_path / "queries.json", tmp_path / "docs.json")
    await cached.encode_queries(["공룡 그림책"])
    await cached.encode_queries(["공룡 그림책", "우주"])
    assert calls == ["check"] and inner.query_calls == [["공룡 그림책"], ["우주"]]
    reread = CachedEmbedder(FakeEmbedder(), tmp_path / "queries.json")
    assert len(await reread.encode_queries(["우주"])) == 1 and reread.encoded == 0
