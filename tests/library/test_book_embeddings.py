"""[catalog/book-embeddings] 저장, 적재 대상, 전체·증분 적재, 기관 범위 유사도 조회.

임베딩 서버 없이 가짜 인코더로 돈다.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.embedding import EmbeddingFailure
from app.library.recommendation import embeddings
from app.library.recommendation.embedding_text import content_hash
from app.library.recommendation.embeddings import run_embedding, similar_books
from tests.conftest import Tenant
from tests.embedding_helpers import FakeEmbedder, toward, unit
from tests.helpers import add_held_book


async def _books(session: AsyncSession, library_id: int, count: int) -> list[int]:
    return [
        (await add_held_book(session, library_id, title=f"책{i}", description=f"소개{i}"))["id"]
        for i in range(count)
    ]


async def _rows(session: AsyncSession) -> list:
    result = await session.execute(
        text(
            "SELECT library_id, library_book_id, model_name, text_version, content_hash,"
            " vector_dims(embedding) AS dims, created_at, updated_at"
            " FROM book_embeddings ORDER BY library_book_id, model_name, text_version"
        )
    )
    return list(result.mappings())


async def _load(session: AsyncSession, embedder: FakeEmbedder, *, full: bool, **options):
    options.setdefault("batch_size", 32)
    return await run_embedding(session, embedder, full=full, **options)


async def test_full_load(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 전체 적재와 증분 적재 / 전체 적재"""
    ids = await _books(session, library_a.id, 5)
    run = await _load(session, FakeEmbedder(), full=True)
    assert (run.targets, run.encoded, run.skipped, run.stopped) == (5, 5, 0, None)
    rows = await _rows(session)
    assert [r["library_book_id"] for r in rows] == ids
    assert {r["dims"] for r in rows} == {1024}
    assert {(r["library_id"], r["model_name"], r["text_version"]) for r in rows} == {
        (library_a.id, "fake-model", 1)
    }


async def test_incremental_rerun_encodes_nothing(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 전체 적재와 증분 적재 / 증분 재실행은 0건"""
    await _books(session, library_a.id, 5)
    await _load(session, FakeEmbedder(), full=True)
    again = FakeEmbedder()
    run = await _load(session, again, full=False)
    assert (run.targets, run.encoded, run.skipped) == (5, 0, 5)
    assert again.document_calls == []


async def test_incremental_encodes_changed_book_only(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/book-embeddings] 전체 적재와 증분 적재 / 바뀐 책만 다시 인코딩"""
    ids = await _books(session, library_a.id, 3)
    await _load(session, FakeEmbedder(), full=True)
    before = {r["library_book_id"]: r for r in await _rows(session)}
    # 같은 트랜잭션에서는 now()가 같아 고친 시각 비교가 안 되므로 저장된 시각을 과거로 둔다
    await session.execute(text("UPDATE book_embeddings SET updated_at = now() - interval '1 day'"))
    await session.execute(
        text("UPDATE library_books SET description = '고친 소개' WHERE id = :id"), {"id": ids[1]}
    )

    again = FakeEmbedder()
    run = await _load(session, again, full=False)
    assert (run.encoded, run.skipped) == (1, 2)
    assert [len(call) for call in again.document_calls] == [1]
    assert "고친 소개" in again.document_calls[0][0]
    after = {r["library_book_id"]: r for r in await _rows(session)}
    assert after[ids[1]]["content_hash"] != before[ids[1]]["content_hash"]
    assert after[ids[1]]["content_hash"] == content_hash(again.document_calls[0][0])
    assert after[ids[1]]["updated_at"] > after[ids[0]]["updated_at"]
    assert after[ids[0]]["content_hash"] == before[ids[0]]["content_hash"]


async def test_incremental_encodes_new_book_only(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 전체 적재와 증분 적재 / 새 책만 인코딩"""
    await _books(session, library_a.id, 2)
    await _load(session, FakeEmbedder(), full=True)
    await add_held_book(session, library_a.id, title="새로 들어온 책")
    again = FakeEmbedder()
    run = await _load(session, again, full=False)
    assert (run.targets, run.encoded, run.skipped) == (3, 1, 2)
    assert again.document_calls == [["새로 들어온 책\n테스트 저자"]]


async def test_batch_size(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 전체 적재와 증분 적재 / 배치 크기"""
    await _books(session, library_a.id, 5)
    embedder = FakeEmbedder()
    progress: list[int] = []
    await _load(
        session, embedder, full=True, batch_size=2, on_progress=lambda r: progress.append(r.done)
    )
    assert [len(call) for call in embedder.document_calls] == [2, 2, 1]
    assert progress == [2, 4, 5]


async def test_full_rerun_encodes_everything_again(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/book-embeddings] 전체 적재와 증분 적재 / 전체 적재는 바뀌지 않은 책도 다시 인코딩

    [catalog/book-embeddings] 벡터와 메타데이터 저장 / 같은 키는 한 행
    """
    ids = await _books(session, library_a.id, 3)
    await _load(session, FakeEmbedder(), full=True)
    again = FakeEmbedder(vectors={"책": unit(1)})
    run = await _load(session, again, full=True)
    assert (run.encoded, run.skipped) == (3, 0)
    assert len(await _rows(session)) == 3
    stored = await session.scalar(
        text("SELECT embedding::text FROM book_embeddings WHERE library_book_id = :id"),
        {"id": ids[0]},
    )
    assert stored.startswith("[1,0,0")  # 두 번째 값으로 바뀌어 있다


async def test_text_versions_coexist(
    session: AsyncSession, library_a: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[catalog/book-embeddings] 벡터와 메타데이터 저장 / 텍스트 버전이 다른 벡터 공존"""
    await _books(session, library_a.id, 1)
    await _load(session, FakeEmbedder(), full=False)
    monkeypatch.setattr(embeddings, "TEXT_VERSION", 2)
    run = await _load(session, FakeEmbedder(), full=False)
    assert run.encoded == 1
    assert [r["text_version"] for r in await _rows(session)] == [1, 2]


async def test_model_names_coexist(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 인코더 교체 / 모델 이름 기록

    [catalog/book-embeddings] 인코더 교체 / 가짜 인코더로 적재와 조회
    """
    await _books(session, library_a.id, 1)
    await _load(session, FakeEmbedder("model-a"), full=False)
    run = await _load(session, FakeEmbedder("model-b"), full=False)
    assert run.encoded == 1
    assert [r["model_name"] for r in await _rows(session)] == ["model-a", "model-b"]
    found = await similar_books(
        session, FakeEmbedder("model-b"), library_id=library_a.id, query="책"
    )
    assert len(found) == 1


async def test_original_text_is_not_stored(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 벡터와 메타데이터 저장 / 원문 미저장"""
    await add_held_book(
        session, library_a.id, title="공룡 대탐험", description="아주 특별한 소개 문구"
    )
    embedder = FakeEmbedder()
    await _load(session, embedder, full=True)
    row = (await session.execute(text("SELECT * FROM book_embeddings"))).mappings().one()
    assert row["content_hash"] == content_hash(embedder.document_calls[0][0])
    assert set(row) == {
        "id",
        "library_id",
        "library_book_id",
        "model_name",
        "text_version",
        "embedding",
        "content_hash",
        "created_at",
        "updated_at",
    }
    assert not any("소개 문구" in str(value) or "공룡" in str(value) for value in row.values())


async def test_books_without_recommendable_holdings_are_skipped(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/book-embeddings] 적재 대상 / 제적·분실 사본만 남은 책"""
    kept = await add_held_book(session, library_a.id, "on_loan", title="대출 중")
    await add_held_book(session, library_a.id, "withdrawn", "lost", title="빠진 책")
    await add_held_book(session, library_a.id, "damaged", title="파손")
    run = await _load(session, FakeEmbedder(), full=True)
    assert run.targets == 1
    assert [r["library_book_id"] for r in await _rows(session)] == [kept["id"]]


async def test_book_without_isbn_is_embedded(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 적재 대상 / ISBN 없는 책 포함"""
    book = await add_held_book(session, library_a.id, isbn=None, title="ISBN 없는 그림책")
    assert book["isbn"] is None and book["book_id"] is None
    await _load(session, FakeEmbedder(), full=True)
    assert [r["library_book_id"] for r in await _rows(session)] == [book["id"]]


async def test_run_for_one_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/book-embeddings] 적재 대상 / 기관을 지정한 실행"""
    await _books(session, library_a.id, 2)
    await add_held_book(session, library_b.id, title="B 기관 책")
    run = await _load(session, FakeEmbedder(), full=True, library_id=library_a.id)
    assert run.targets == 2
    assert {r["library_id"] for r in await _rows(session)} == {library_a.id}

    everyone = await _load(session, FakeEmbedder(), full=False)
    assert (everyone.targets, everyone.encoded, everyone.skipped) == (3, 1, 2)
    assert {r["library_id"] for r in await _rows(session)} == {library_a.id, library_b.id}


async def test_failure_keeps_finished_batches(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 운영자 실행의 출력과 중단 / 중간 실패 뒤 이어 하기"""
    await _books(session, library_a.id, 5)
    run = await _load(session, FakeEmbedder(fail_on=2), full=True, batch_size=2)
    assert run.stopped is not None and run.stopped.failure is EmbeddingFailure.SERVER_ERROR
    assert (run.encoded, len(await _rows(session))) == (2, 2)

    resumed = FakeEmbedder()
    rest = await _load(session, resumed, full=False, batch_size=2)
    assert (rest.encoded, rest.skipped, rest.stopped) == (3, 2, None)
    assert len(await _rows(session)) == 5


async def _similarity_setup(session: AsyncSession, library_id: int, cosines: dict[str, float]):
    """서명마다 질의 벡터 `unit(1)`과의 유사도를 정한 책을 만들고 적재한다."""
    ids = {
        title: (await add_held_book(session, library_id, title=title))["id"] for title in cosines
    }
    embedder = FakeEmbedder(
        vectors={"질의": unit(1), **{title: toward(c) for title, c in cosines.items()}}
    )
    await _load(session, embedder, full=True, library_id=library_id)
    return ids, embedder


async def test_similar_books_in_order(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 기관 범위 유사도 조회 / 유사도 순서"""
    cosines = {"가": 0.2, "나": 0.9, "다": 0.5, "라": 0.7, "마": 0.1, "바": 0.3}
    ids, embedder = await _similarity_setup(session, library_a.id, cosines)
    found = await similar_books(session, embedder, library_id=library_a.id, query="질의")
    assert [f.library_book.id for f in found] == [ids[t] for t in ("나", "라", "다", "바", "가")]
    assert [f.similarity for f in found] == pytest.approx([0.9, 0.7, 0.5, 0.3, 0.2], abs=1e-5)
    assert embedder.query_calls == [["질의"]]


async def test_similar_books_stay_in_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/book-embeddings] 기관 범위 유사도 조회 / 다른 기관의 책"""
    mine, embedder = await _similarity_setup(session, library_a.id, {"우리": 0.3})
    await _similarity_setup(session, library_b.id, {"남의": 0.99})
    found = await similar_books(session, embedder, library_id=library_a.id, query="질의")
    assert [f.library_book.id for f in found] == [mine["우리"]]
    assert {f.library_book.library_id for f in found} == {library_a.id}


async def test_similar_books_drop_withdrawn(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 기관 범위 유사도 조회 / 적재 뒤 제적된 책"""
    ids, embedder = await _similarity_setup(session, library_a.id, {"남는": 0.4, "빠질": 0.9})
    await session.execute(
        text("UPDATE holdings SET status = 'withdrawn' WHERE library_book_id = :id"),
        {"id": ids["빠질"]},
    )
    found = await similar_books(session, embedder, library_id=library_a.id, query="질의")
    assert [f.library_book.id for f in found] == [ids["남는"]]


async def test_similar_books_ignore_other_models(
    session: AsyncSession, library_a: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[catalog/book-embeddings] 기관 범위 유사도 조회 / 다른 모델의 벡터"""
    ids, embedder = await _similarity_setup(session, library_a.id, {"책": 0.4})
    other = FakeEmbedder("other-model", vectors={"책": unit(1)})
    await _load(session, other, full=True)
    monkeypatch.setattr(embeddings, "TEXT_VERSION", 2)
    await _load(session, FakeEmbedder(vectors={"책": unit(1)}), full=True)
    monkeypatch.undo()

    found = await similar_books(session, embedder, library_id=library_a.id, query="질의")
    assert [f.library_book.id for f in found] == [ids["책"]]
    assert found[0].similarity == pytest.approx(0.4, abs=1e-5)


async def test_similar_books_before_loading(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 기관 범위 유사도 조회 / 적재 전 조회"""
    await _books(session, library_a.id, 2)
    assert await similar_books(session, FakeEmbedder(), library_id=library_a.id, query="책") == []
