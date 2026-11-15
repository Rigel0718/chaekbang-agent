"""[catalog/book-embeddings] 두 층 저장, 적재 대상, 전체·증분 적재, 기관 범위 유사도 조회.

공식 서지에 연결된 책은 공식 서지 벡터, 연결되지 않은 책은 기관 도서 벡터. 임베딩 서버 없이 가짜
인코더로 돈다.
"""

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.embedding import EmbeddingFailure
from app.central.embedding_text import official_embedding_text
from app.central.models import Book
from app.central.official_embeddings import run_official_embedding
from app.core import embedding_text as rules
from app.core.embedding_text import TextKind, content_hash
from app.library.models.catalog import LibraryBook
from app.library.recommendation.embeddings import (
    book_vectors,
    held_official_ids,
    missing_official_descriptions,
    run_library_embedding,
    similar_books,
)
from tests.conftest import Tenant
from tests.embedding_helpers import FakeEmbedder, toward, unit
from tests.helpers import add_book, add_held_book, add_holding, add_library_book, make_isbn

_numbers = iter(range(700, 10_000))


async def _own_books(session: AsyncSession, library_id: int, count: int, **values) -> list[int]:
    """공식 서지 없는 책(ISBN 없음)."""
    return [
        (
            await add_held_book(
                session, library_id, title=f"책{i}", description=f"소개{i}", **values
            )
        )["id"]
        for i in range(count)
    ]


async def _official(session: AsyncSession, **values) -> dict:
    defaults = {"title": "공식 서명", "description": "공식 소개"}
    return await add_book(session, make_isbn(next(_numbers)), **{**defaults, **values})


async def _hold(session: AsyncSession, library_id: int, book: dict, *statuses: str, **values):
    """공식 서지에 연결된 기관 도서와 사본."""
    values.setdefault("title", f"기관 서명 {book['id']}")
    library_book = await add_library_book(
        session, library_id, book["isbn"], book_id=book["id"], **values
    )
    for status in statuses or ("available",):
        await add_holding(
            session, library_id, library_book["id"], f"EB{next(_numbers):05d}", status=status
        )
    return library_book


async def _officials(session: AsyncSession, library_id: int, count: int) -> list[int]:
    ids = []
    for i in range(count):
        book = await _official(session, title=f"공식{i}", description=f"공식 소개{i}")
        await _hold(session, library_id, book)
        ids.append(book["id"])
    return ids


async def _official_rows(session: AsyncSession) -> list:
    result = await session.execute(
        text(
            "SELECT book_id, model_name, text_version, kind, content_hash,"
            " vector_dims(embedding) AS dims, created_at, updated_at"
            " FROM official_book_embeddings ORDER BY book_id, model_name, text_version, kind"
        )
    )
    return list(result.mappings())


async def _own_rows(session: AsyncSession) -> list:
    result = await session.execute(
        text(
            "SELECT library_id, library_book_id, model_name, text_version, kind, content_hash,"
            " vector_dims(embedding) AS dims, created_at, updated_at"
            " FROM book_embeddings ORDER BY library_book_id, model_name, text_version, kind"
        )
    )
    return list(result.mappings())


async def _load_official(session, embedder, *, full: bool, **options):
    options.setdefault("batch_size", 32)
    return await run_official_embedding(session, embedder, full=full, **options)


async def _load_own(session, embedder, *, full: bool, **options):
    options.setdefault("batch_size", 32)
    return await run_library_embedding(session, embedder, full=full, **options)


async def _load_both(session, embedder, *, full: bool, library_id: int | None = None):
    within = held_official_ids(library_id) if library_id is not None else None
    official = await _load_official(session, embedder, full=full, within=within)
    own = await _load_own(session, embedder, full=full, library_id=library_id)
    return official, own


# --- 전체·증분 적재 ---


async def test_full_load(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 전체 적재와 증분 적재 / 전체 적재"""
    official_ids = await _officials(session, library_a.id, 5)
    own_ids = await _own_books(session, library_a.id, 5)
    official, own = await _load_both(session, FakeEmbedder(), full=True)
    assert (official.targets, official.encoded, official.skipped, official.stopped) == (
        5,
        5,
        0,
        None,
    )
    assert (own.targets, own.encoded, own.skipped, own.stopped) == (5, 5, 0, None)
    rows = await _official_rows(session)
    assert [r["book_id"] for r in rows] == official_ids
    assert {(r["model_name"], r["text_version"], r["kind"], r["dims"]) for r in rows} == {
        ("fake-model", rules.TEXT_VERSION, "full", 1024)
    }
    own_rows = await _own_rows(session)
    assert [r["library_book_id"] for r in own_rows] == own_ids
    assert {(r["library_id"], r["kind"], r["dims"]) for r in own_rows} == {
        (library_a.id, "full", 1024)
    }


async def test_incremental_rerun_encodes_nothing(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 전체 적재와 증분 적재 / 증분 재실행은 0건"""
    await _officials(session, library_a.id, 3)
    await _own_books(session, library_a.id, 2)
    await _load_both(session, FakeEmbedder(), full=True)
    again = FakeEmbedder()
    official, own = await _load_both(session, again, full=False)
    assert (official.targets, official.encoded, official.skipped) == (3, 0, 3)
    assert (own.targets, own.encoded, own.skipped) == (2, 0, 2)
    assert again.document_calls == []


async def test_incremental_encodes_changed_book_only(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/book-embeddings] 전체 적재와 증분 적재 / 바뀐 책만 다시 인코딩"""
    ids = await _own_books(session, library_a.id, 3)
    await _load_own(session, FakeEmbedder(), full=True)
    before = {r["library_book_id"]: r for r in await _own_rows(session)}
    # 같은 트랜잭션에서는 now()가 같아 고친 시각 비교가 안 되므로 저장된 시각을 과거로 둔다
    await session.execute(text("UPDATE book_embeddings SET updated_at = now() - interval '1 day'"))
    await session.execute(
        text("UPDATE library_books SET description = '고친 소개' WHERE id = :id"), {"id": ids[1]}
    )

    again = FakeEmbedder()
    run = await _load_own(session, again, full=False)
    assert (run.encoded, run.skipped) == (1, 2)
    assert [len(call) for call in again.document_calls] == [1]
    assert "고친 소개" in again.document_calls[0][0]
    after = {r["library_book_id"]: r for r in await _own_rows(session)}
    assert after[ids[1]]["content_hash"] != before[ids[1]]["content_hash"]
    assert after[ids[1]]["content_hash"] == content_hash(again.document_calls[0][0])
    assert after[ids[1]]["updated_at"] > after[ids[0]]["updated_at"]
    assert after[ids[0]]["content_hash"] == before[ids[0]]["content_hash"]


async def test_incremental_encodes_new_official_only(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/book-embeddings] 전체 적재와 증분 적재 / 새 책만 인코딩"""
    await _officials(session, library_a.id, 2)
    await _load_official(session, FakeEmbedder(), full=True)
    await _official(session, title="새로 생긴 공식 서지", description=None)
    again = FakeEmbedder()
    run = await _load_official(session, again, full=False)
    assert (run.targets, run.encoded, run.skipped) == (3, 1, 2)
    assert again.document_calls == [["새로 생긴 공식 서지"]]


async def test_later_linked_book(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 전체 적재와 증분 적재 / 나중에 연결된 책"""
    (own_id,) = await _own_books(session, library_a.id, 1)
    await _load_both(session, FakeEmbedder(), full=True)
    book = await _official(session, title="이제 연결된 책")
    await session.execute(
        text("UPDATE library_books SET book_id = :book, isbn = :isbn WHERE id = :id"),
        {"book": book["id"], "isbn": book["isbn"], "id": own_id},
    )
    again = FakeEmbedder()
    official, own = await _load_both(session, again, full=False)
    assert (official.encoded, own.targets, own.encoded) == (1, 0, 0)
    assert [r["book_id"] for r in await _official_rows(session)] == [book["id"]]
    assert [r["library_book_id"] for r in await _own_rows(session)] == [own_id]  # 지우지 않는다


async def test_batch_size(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 전체 적재와 증분 적재 / 배치 크기"""
    await _officials(session, library_a.id, 5)
    embedder = FakeEmbedder()
    progress: list[int] = []
    await _load_official(
        session, embedder, full=True, batch_size=2, on_progress=lambda r: progress.append(r.done)
    )
    assert [len(call) for call in embedder.document_calls] == [2, 2, 1]
    assert progress == [2, 4, 5]


async def test_default_batch_size(
    session: AsyncSession, library_a: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[catalog/book-embeddings] 전체 적재와 증분 적재 / 배치 기본값"""
    from app.core.config import Settings, get_settings

    assert Settings.model_fields["embedding_batch_size"].default == 4
    monkeypatch.setattr(get_settings(), "embedding_batch_size", 4)  # .env 값과 상관없이 기본값으로
    await _own_books(session, library_a.id, 5)
    embedder = FakeEmbedder()
    await run_library_embedding(session, embedder, full=True)
    assert [len(call) for call in embedder.document_calls] == [4, 1]


async def test_full_rerun_encodes_everything_again(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/book-embeddings] 전체 적재와 증분 적재 / 전체 적재는 바뀌지 않은 책도 다시 인코딩

    [catalog/book-embeddings] 벡터와 메타데이터 저장 / 같은 키는 한 행
    """
    ids = await _officials(session, library_a.id, 3)
    await _load_official(session, FakeEmbedder(), full=True)
    again = FakeEmbedder(vectors={"공식": unit(1)})
    run = await _load_official(session, again, full=True)
    assert (run.encoded, run.skipped) == (3, 0)
    assert len(await _official_rows(session)) == 3
    stored = await session.scalar(
        text("SELECT embedding::text FROM official_book_embeddings WHERE book_id = :id"),
        {"id": ids[0]},
    )
    assert stored.startswith("[1,0,0")  # 두 번째 값으로 바뀌어 있다


async def test_failure_keeps_finished_batches(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 운영자 실행의 출력과 중단 / 중간 실패 뒤 이어 하기"""
    await _officials(session, library_a.id, 5)
    run = await _load_official(session, FakeEmbedder(fail_on=2), full=True, batch_size=2)
    assert run.stopped is not None and run.stopped.failure is EmbeddingFailure.SERVER_ERROR
    assert (run.encoded, len(await _official_rows(session))) == (2, 2)

    rest = await _load_official(session, FakeEmbedder(), full=False, batch_size=2)
    assert (rest.encoded, rest.skipped, rest.stopped) == (3, 2, None)
    assert len(await _official_rows(session)) == 5


# --- 저장 ---


async def test_text_versions_coexist(
    session: AsyncSession, library_a: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[catalog/book-embeddings] 벡터와 메타데이터 저장 / 텍스트 버전이 다른 벡터 공존"""
    await _officials(session, library_a.id, 1)
    await _own_books(session, library_a.id, 1)
    await _load_both(session, FakeEmbedder(), full=False)
    monkeypatch.setattr(rules, "TEXT_VERSION", rules.TEXT_VERSION + 1)
    official, own = await _load_both(session, FakeEmbedder(), full=False)
    assert (official.encoded, own.encoded) == (1, 1)
    versions = [rules.TEXT_VERSION - 1, rules.TEXT_VERSION]
    assert [r["text_version"] for r in await _official_rows(session)] == versions
    assert [r["text_version"] for r in await _own_rows(session)] == versions


async def test_model_names_coexist(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 인코더 교체 / 모델 이름 기록

    [catalog/book-embeddings] 인코더 교체 / 가짜 인코더로 적재와 조회
    """
    await _officials(session, library_a.id, 1)
    await _load_official(session, FakeEmbedder("model-a"), full=False)
    run = await _load_official(session, FakeEmbedder("model-b"), full=False)
    assert run.encoded == 1
    assert [r["model_name"] for r in await _official_rows(session)] == ["model-a", "model-b"]
    found = await similar_books(
        session, FakeEmbedder("model-b"), library_id=library_a.id, query="책"
    )
    assert len(found) == 1


async def test_original_text_is_not_stored(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 벡터와 메타데이터 저장 / 원문 미저장"""
    book = await _official(session, title="공룡 대탐험", description="아주 특별한 공식 소개 문구")
    await _hold(session, library_a.id, book)
    await add_held_book(session, library_a.id, title="고양이 탐정", description="기관 소개 문구")
    embedder = FakeEmbedder()
    await _load_both(session, embedder, full=True)
    texts = [t for call in embedder.document_calls for t in call]
    columns = {
        "official_book_embeddings": {"id", "book_id"},
        "book_embeddings": {"id", "library_id", "library_book_id"},
    }
    for table, keys in columns.items():
        row = (await session.execute(text(f"SELECT * FROM {table}"))).mappings().one()
        assert row["content_hash"] in {content_hash(t) for t in texts}
        assert set(row) == keys | {
            "model_name",
            "text_version",
            "kind",
            "embedding",
            "content_hash",
            "created_at",
            "updated_at",
        }
        values = [str(value) for value in row.values()]
        assert not any("소개 문구" in v or "공룡" in v or "고양이" in v for v in values)


async def test_default_kind_is_full(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 벡터 종류 / 기본 종류"""
    await _officials(session, library_a.id, 1)
    await _own_books(session, library_a.id, 1)
    await run_official_embedding(session, FakeEmbedder(), full=True)
    await run_library_embedding(session, FakeEmbedder(), full=True)
    assert [r["kind"] for r in await _official_rows(session)] == ["full"]
    assert [r["kind"] for r in await _own_rows(session)] == ["full"]


# --- 적재 대상 ---


async def test_books_without_recommendable_holdings_are_skipped(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/book-embeddings] 적재 대상 / 제적·분실 사본만 남은 책"""
    kept = await add_held_book(session, library_a.id, "on_loan", title="대출 중")
    await add_held_book(session, library_a.id, "withdrawn", "lost", title="빠진 책")
    await add_held_book(session, library_a.id, "damaged", title="파손")
    run = await _load_own(session, FakeEmbedder(), full=True)
    assert run.targets == 1
    assert [r["library_book_id"] for r in await _own_rows(session)] == [kept["id"]]


async def test_book_without_isbn_is_embedded(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 적재 대상 / ISBN 없는 책 포함"""
    book = await add_held_book(session, library_a.id, isbn=None, title="ISBN 없는 그림책")
    assert book["isbn"] is None and book["book_id"] is None
    await _load_own(session, FakeEmbedder(), full=True)
    assert [r["library_book_id"] for r in await _own_rows(session)] == [book["id"]]


async def test_linked_book_uses_official_vector_only(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/book-embeddings] 적재 대상 / 연결된 책은 공식 서지 벡터만"""
    book = await _official(session)
    await _hold(session, library_a.id, book)
    official, own = await _load_both(session, FakeEmbedder(), full=True)
    assert (official.encoded, own.targets) == (1, 0)
    assert [r["book_id"] for r in await _official_rows(session)] == [book["id"]]
    assert await _own_rows(session) == []


async def test_shared_book_encoded_once(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/book-embeddings] 적재 대상 / 두 기관이 가진 같은 책"""
    book = await _official(session)
    await _hold(session, library_a.id, book)
    await _hold(session, library_b.id, book)
    embedder = FakeEmbedder()
    official, _ = await _load_both(session, embedder, full=True)
    assert official.encoded == 1
    assert sum(len(call) for call in embedder.document_calls) == 1
    assert len(await _official_rows(session)) == 1


async def test_run_for_one_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/book-embeddings] 적재 대상 / 기관을 지정한 실행"""
    mine = await _official(session, title="A의 공식 서지")
    theirs = await _official(session, title="B의 공식 서지")
    await _hold(session, library_a.id, mine)
    await _hold(session, library_b.id, theirs)
    (own_a,) = await _own_books(session, library_a.id, 1)
    await add_held_book(session, library_b.id, title="B 기관 책")

    official, own = await _load_both(session, FakeEmbedder(), full=True, library_id=library_a.id)
    assert (official.targets, own.targets) == (1, 1)
    assert [r["book_id"] for r in await _official_rows(session)] == [mine["id"]]
    assert [r["library_book_id"] for r in await _own_rows(session)] == [own_a]

    official, own = await _load_both(session, FakeEmbedder(), full=False)
    assert (official.encoded, own.encoded) == (1, 1)
    assert {r["library_id"] for r in await _own_rows(session)} == {library_a.id, library_b.id}


# --- 공식 서지 벡터에 기관 값 없음 ---


async def test_official_vector_ignores_library_values(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/book-embeddings] 공식 서지 벡터에 기관 값 없음 / 기관마다 다른 값"""
    book = await _official(session, title="공식 서명", description="공식 소개", kdc=None)
    await _hold(
        session,
        library_a.id,
        book,
        title="A 서명",
        author="A 저자",
        kdc="813",
        description="A 소개",
    )
    await _hold(
        session,
        library_b.id,
        book,
        title="B 서명",
        author="B 저자",
        kdc="490",
        description="B 소개",
    )
    embedder = FakeEmbedder()
    await _load_official(session, embedder, full=True)
    official = await session.get(Book, book["id"])
    expected = content_hash(official_embedding_text(official))
    assert [r["content_hash"] for r in await _official_rows(session)] == [expected]
    assert embedder.document_calls == [["공식 서명\n공식 소개"]]


async def test_official_without_description_ignores_library_description(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/book-embeddings] 공식 서지 벡터에 기관 값 없음 / 공식 서지에 없는 소개"""
    book = await _official(session, title="소개 없는 공식", description=None)
    await _hold(session, library_a.id, book, description="기관에만 있는 소개")
    embedder = FakeEmbedder()
    await _load_official(session, embedder, full=True)
    assert embedder.document_calls == [["소개 없는 공식"]]
    assert await missing_official_descriptions(session) == (1, 1)


async def test_editing_library_values_changes_nothing(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/book-embeddings] 공식 서지 벡터에 기관 값 없음 / 기관 값을 고쳐도 그대로"""
    book = await _official(session)
    library_book = await _hold(session, library_a.id, book)
    await _load_both(session, FakeEmbedder(), full=True)
    await session.execute(
        text(
            "UPDATE library_books SET title = '고친 서명', description = '고친 소개' WHERE id = :id"
        ),
        {"id": library_book["id"]},
    )
    official, own = await _load_both(session, FakeEmbedder(), full=False)
    assert (official.encoded, own.encoded) == (0, 0)


# --- 조회 ---


async def _similarity_setup(
    session: AsyncSession,
    library_id: int,
    cosines: dict[str, float],
    *,
    linked: set[str] = frozenset(),
):
    """서명마다 질의 벡터 `unit(1)`과의 유사도를 정한 책을 만들고 적재한다.

    linked에 든 서명은 공식 서지에 연결된 책으로 만든다.
    """
    ids = {}
    for title, _ in cosines.items():
        if title in linked:
            book = await _official(session, title=title, description=None)
            ids[title] = (await _hold(session, library_id, book, title=f"기관 {title}"))["id"]
        else:
            ids[title] = (await add_held_book(session, library_id, title=title))["id"]
    embedder = FakeEmbedder(
        vectors={"질의": unit(1), **{title: toward(c) for title, c in cosines.items()}}
    )
    await _load_both(session, embedder, full=True, library_id=library_id)
    return ids, embedder


async def test_similar_books_in_order(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 기관 범위 유사도 조회 / 유사도 순서"""
    cosines = {"가": 0.2, "나": 0.9, "다": 0.5, "라": 0.7, "마": 0.1, "바": 0.3}
    ids, embedder = await _similarity_setup(session, library_a.id, cosines)
    found = await similar_books(session, embedder, library_id=library_a.id, query="질의")
    assert [f.library_book.id for f in found] == [ids[t] for t in ("나", "라", "다", "바", "가")]
    assert [f.similarity for f in found] == pytest.approx([0.9, 0.7, 0.5, 0.3, 0.2], abs=1e-5)
    assert embedder.query_calls == [["질의"]]


async def test_similar_books_merge_layers(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 기관 범위 유사도 조회 / 두 층이 한 순위로"""
    cosines = {"가": 0.9, "나": 0.8, "다": 0.7, "라": 0.6, "마": 0.5, "바": 0.4}
    ids, embedder = await _similarity_setup(
        session, library_a.id, cosines, linked={"가", "다", "마"}
    )
    found = await similar_books(session, embedder, library_id=library_a.id, query="질의", limit=6)
    assert [f.library_book.id for f in found] == [ids[t] for t in cosines]
    assert [f.similarity for f in found] == pytest.approx(list(cosines.values()), abs=1e-5)
    assert [f.library_book.book_id is not None for f in found] == [True, False] * 3


async def test_similar_books_stay_in_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/book-embeddings] 기관 범위 유사도 조회 / 다른 기관의 책"""
    mine, embedder = await _similarity_setup(session, library_a.id, {"우리": 0.3})
    await _similarity_setup(session, library_b.id, {"남의": 0.99})
    found = await similar_books(session, embedder, library_id=library_a.id, query="질의")
    assert [f.library_book.id for f in found] == [mine["우리"]]
    assert {f.library_book.library_id for f in found} == {library_a.id}


async def test_similar_books_skip_official_held_elsewhere(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/book-embeddings] 기관 범위 유사도 조회 / 다른 기관만 가진 공식 서지"""
    mine, embedder = await _similarity_setup(session, library_a.id, {"우리": 0.3}, linked={"우리"})
    await _similarity_setup(session, library_b.id, {"남의": 0.99}, linked={"남의"})
    found = await similar_books(session, embedder, library_id=library_a.id, query="질의")
    assert [f.library_book.id for f in found] == [mine["우리"]]


async def test_similar_books_shared_book_once(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/book-embeddings] 기관 범위 유사도 조회 / 두 기관이 가진 같은 책"""
    book = await _official(session, title="함께 가진 책", description=None)
    mine = await _hold(session, library_a.id, book)
    await _hold(session, library_b.id, book)
    embedder = FakeEmbedder(vectors={"질의": unit(1), "함께": toward(0.8)})
    await _load_both(session, embedder, full=True)
    found = await similar_books(session, embedder, library_id=library_a.id, query="질의")
    assert [(f.library_book.id, f.library_book.library_id) for f in found] == [
        (mine["id"], library_a.id)
    ]


async def test_similar_books_drop_withdrawn(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 기관 범위 유사도 조회 / 적재 뒤 제적된 책"""
    ids, embedder = await _similarity_setup(
        session, library_a.id, {"남는": 0.4, "빠질": 0.9}, linked={"남는", "빠질"}
    )
    await session.execute(
        text("UPDATE holdings SET status = 'withdrawn' WHERE library_book_id = :id"),
        {"id": ids["빠질"]},
    )
    found = await similar_books(session, embedder, library_id=library_a.id, query="질의")
    assert [f.library_book.id for f in found] == [ids["남는"]]


async def test_similar_books_ignore_leftover_own_vector(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/book-embeddings] 기관 범위 유사도 조회 / 연결된 책에 남은 기관 도서 벡터"""
    own = await add_held_book(session, library_a.id, title="옛 벡터")
    embedder = FakeEmbedder(
        vectors={"질의": unit(1), "옛 벡터": toward(0.9), "새 공식": toward(0.3)}
    )
    await _load_own(session, embedder, full=True)
    book = await _official(session, title="새 공식", description=None)
    await session.execute(
        text("UPDATE library_books SET book_id = :book, isbn = :isbn WHERE id = :id"),
        {"book": book["id"], "isbn": book["isbn"], "id": own["id"]},
    )
    await _load_official(session, embedder, full=False)
    assert len(await _own_rows(session)) == 1  # 남아 있다
    found = await similar_books(session, embedder, library_id=library_a.id, query="질의")
    assert [f.library_book.id for f in found] == [own["id"]]
    assert found[0].similarity == pytest.approx(0.3, abs=1e-5)


async def test_similar_books_ignore_other_models(
    session: AsyncSession, library_a: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[catalog/book-embeddings] 기관 범위 유사도 조회 / 다른 모델의 벡터"""
    ids, embedder = await _similarity_setup(
        session, library_a.id, {"책": 0.4, "바다": 0.2}, linked={"바다"}
    )
    near = {"책": unit(1), "바다": unit(1)}
    await _load_both(session, FakeEmbedder("other-model", vectors=near), full=True)
    monkeypatch.setattr(rules, "TEXT_VERSION", rules.TEXT_VERSION + 1)
    await _load_both(session, FakeEmbedder(vectors=near), full=True)
    monkeypatch.undo()

    found = await similar_books(session, embedder, library_id=library_a.id, query="질의")
    assert [f.library_book.id for f in found] == [ids["책"], ids["바다"]]
    assert [f.similarity for f in found] == pytest.approx([0.4, 0.2], abs=1e-5)


async def test_similar_books_ignore_other_kinds(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 벡터 종류 / 종류가 다른 벡터 공존"""
    ids, embedder = await _similarity_setup(session, library_a.id, {"책": 0.4}, linked={"책"})
    await session.execute(
        text(
            "INSERT INTO official_book_embeddings"
            " (book_id, model_name, text_version, kind, embedding, content_hash)"
            " SELECT book_id, model_name, text_version, 'description', :vector, content_hash"
            " FROM official_book_embeddings"
        ),
        {"vector": str(unit(1)).replace(" ", "")},
    )
    found = await similar_books(session, embedder, library_id=library_a.id, query="질의")
    assert [f.library_book.id for f in found] == [ids["책"]]
    assert found[0].similarity == pytest.approx(0.4, abs=1e-5)


async def test_similar_books_before_loading(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 기관 범위 유사도 조회 / 적재 전 조회"""
    await _own_books(session, library_a.id, 2)
    await _officials(session, library_a.id, 2)
    assert await similar_books(session, FakeEmbedder(), library_id=library_a.id, query="책") == []


# --- 조회 넓히기 (add-recommendation-experiments) ---


def _only(ids: list[int]):
    return select(LibraryBook.id).where(LibraryBook.id.in_(ids))


async def test_similar_books_filter_before_ranking(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/book-embeddings] 유사도 조회 범위와 깊이 / 조건을 먼저"""
    cosines = {"가": 0.9, "나": 0.8, "다": 0.7, "라": 0.6, "마": 0.5, "바": 0.4, "사": 0.3}
    ids, embedder = await _similarity_setup(session, library_a.id, cosines, linked={"라", "바"})
    inside = [ids[t] for t in ("라", "마", "바", "사")]
    found = await similar_books(
        session, embedder, library_id=library_a.id, query="질의", limit=5, within=_only(inside)
    )
    assert [f.library_book.id for f in found] == inside


async def test_similar_books_deep(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 유사도 조회 범위와 깊이 / 깊은 조회"""
    cosines = {f"깊은{i:02d}": 0.95 - i * 0.02 for i in range(40)}
    ids, embedder = await _similarity_setup(session, library_a.id, cosines)
    found = await similar_books(session, embedder, library_id=library_a.id, query="질의", limit=30)
    assert [f.library_book.id for f in found] == [ids[f"깊은{i:02d}"] for i in range(30)]
    assert len(await similar_books(session, embedder, library_id=library_a.id, query="질의")) == 5


async def test_similar_books_condition_naming_other_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/book-embeddings] 유사도 조회 범위와 깊이 / 조건이 다른 기관의 책을 가리킴"""
    mine, embedder = await _similarity_setup(session, library_a.id, {"우리": 0.3})
    theirs, _ = await _similarity_setup(session, library_b.id, {"남의": 0.99}, linked={"남의"})
    found = await similar_books(
        session,
        embedder,
        library_id=library_a.id,
        query="질의",
        within=_only([theirs["남의"], mine["우리"]]),
    )
    assert [f.library_book.id for f in found] == [mine["우리"]]


async def _add_kind(session: AsyncSession, library_book_id: int, kind: str, cosine: float) -> None:
    """이미 `full` 벡터가 있는 책에 다른 종류의 벡터를 직접 넣는다(어느 층이든)."""
    vector = str(toward(cosine)).replace(" ", "")
    for table, key in (("official_book_embeddings", "book_id"), ("book_embeddings", "id")):
        owner = "library_id, library_book_id, " if key == "id" else "book_id, "
        match = (
            "e.library_book_id = :id"
            if key == "id"
            else "e.book_id = (SELECT book_id FROM library_books WHERE id = :id)"
        )
        await session.execute(
            text(
                f"INSERT INTO {table} ({owner}model_name, text_version, kind, embedding,"
                f" content_hash) SELECT {owner}model_name, text_version, :kind, :vector,"
                f" content_hash FROM {table} e WHERE kind = 'full' AND {match}"
            ),
            {"id": library_book_id, "kind": kind, "vector": vector},
        )


async def test_similar_books_weighted_average(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-embeddings] 여러 종류를 합친 유사도 / 가중 평균"""
    ids, embedder = await _similarity_setup(
        session, library_a.id, {"공식책": 0.5, "기관쪽": 0.5}, linked={"공식책"}
    )
    for book_id in ids.values():
        await _add_kind(session, book_id, "title", 0.2)
        await _add_kind(session, book_id, "description", 0.8)
    found = await similar_books(
        session,
        embedder,
        library_id=library_a.id,
        query="질의",
        weights={TextKind.TITLE: 1, TextKind.DESCRIPTION: 3},
    )
    assert {f.library_book.id for f in found} == set(ids.values())
    assert [f.similarity for f in found] == pytest.approx([0.65, 0.65], abs=1e-5)


async def test_similar_books_average_skips_missing_kind(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/book-embeddings] 여러 종류를 합친 유사도 / 없는 종류는 빼고 평균"""
    ids, embedder = await _similarity_setup(session, library_a.id, {"둘다": 0.5, "서명만": 0.5})
    await _add_kind(session, ids["둘다"], "title", 0.2)
    await _add_kind(session, ids["둘다"], "description", 0.8)
    await _add_kind(session, ids["서명만"], "title", 0.4)
    extra = (await add_held_book(session, library_a.id, title="벡터 없음"))["id"]
    found = await similar_books(
        session,
        embedder,
        library_id=library_a.id,
        query="질의",
        weights={TextKind.TITLE: 1, TextKind.DESCRIPTION: 1},
    )
    scores = {f.library_book.id: f.similarity for f in found}
    assert scores == pytest.approx({ids["둘다"]: 0.5, ids["서명만"]: 0.4}, abs=1e-5)
    assert extra not in scores


async def test_similar_books_single_kind_weight_is_the_same(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/book-embeddings] 여러 종류를 합친 유사도 / 종류 하나는 지금과 같음"""
    cosines = {"가": 0.9, "나": 0.8, "다": 0.7, "라": 0.6}
    _, embedder = await _similarity_setup(session, library_a.id, cosines, linked={"가", "다"})
    plain = await similar_books(session, embedder, library_id=library_a.id, query="질의")
    weighted = await similar_books(
        session, embedder, library_id=library_a.id, query="질의", weights={TextKind.FULL: 1}
    )
    assert [f.library_book.id for f in weighted] == [f.library_book.id for f in plain]
    assert [f.similarity for f in weighted] == pytest.approx([f.similarity for f in plain])


async def test_book_vectors_from_both_layers(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/topic-recommendation] 결과 다양화 (책 사이 유사도에 쓰는 저장된 벡터)

    두 층의 벡터를 돌려주고 다른 기관의 id는 빠진다.
    """
    ids, embedder = await _similarity_setup(
        session, library_a.id, {"공식책": 0.9, "기관쪽": 0.4}, linked={"공식책"}
    )
    theirs, _ = await _similarity_setup(session, library_b.id, {"남의": 0.99})
    vectors = await book_vectors(
        session, embedder.name, library_a.id, [*ids.values(), theirs["남의"]]
    )
    assert set(vectors) == set(ids.values())
    assert vectors[ids["공식책"]][0] == pytest.approx(0.9, abs=1e-5)
    assert vectors[ids["기관쪽"]][0] == pytest.approx(0.4, abs=1e-5)
    assert len(vectors[ids["공식책"]]) == 1024
