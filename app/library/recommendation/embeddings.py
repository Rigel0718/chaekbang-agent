"""기관 도서 임베딩의 적재와 조회.

대상은 추천 가능한 기관 도서다(`search.py`의 추천 가능 조건). 인코딩 호출 동안 트랜잭션을 잡지
않고, 배치마다 저장을 끝낸다. 중간에 멈춰도 끝난 배치는 남고 증분 적재로 이어 한다.
텍스트 원문은 저장하지 않는다. 벡터, 모델 이름, 텍스트 버전, 해시만 둔다.
"""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Select, and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.embedding import Embedder, EmbeddingError, EmbeddingFailure
from app.library.models.catalog import Holding, LibraryBook
from app.library.models.embedding import BookEmbedding
from app.library.recommendation.embedding_text import (
    TEXT_VERSION,
    build_embedding_text,
    content_hash,
)
from app.library.recommendation.search import RECOMMENDABLE_STATUSES, recommendable_ids

SIMILAR_LIMIT = 5


@dataclass
class EmbeddingRun:
    targets: int = 0  # 대상 도서 수
    encoded: int = 0
    skipped: int = 0  # 해시가 같아 건너뛴 수
    stopped: EmbeddingError | None = None

    @property
    def done(self) -> int:
        return self.encoded + self.skipped


@dataclass(frozen=True)
class SimilarBook:
    library_book: LibraryBook
    similarity: float  # 코사인 유사도


@dataclass(frozen=True)
class _Pending:
    library_id: int
    library_book_id: int
    text: str
    hash: str


def _target_ids(library_id: int | None) -> Select:
    """추천 가능한 기관 도서 id. 기관을 주지 않는 것은 운영자 실행뿐이다."""
    if library_id is not None:
        return recommendable_ids(library_id)
    return (
        select(Holding.library_book_id).where(Holding.status.in_(RECOMMENDABLE_STATUSES)).distinct()
    )


async def _stored_hashes(session: AsyncSession, model_name: str, ids: list[int]) -> dict[int, str]:
    rows = await session.execute(
        select(BookEmbedding.library_book_id, BookEmbedding.content_hash).where(
            BookEmbedding.library_book_id.in_(ids),
            BookEmbedding.model_name == model_name,
            BookEmbedding.text_version == TEXT_VERSION,
        )
    )
    return {book_id: stored for book_id, stored in rows}


async def _save(
    session: AsyncSession, model_name: str, pending: list[_Pending], vectors: list[list[float]]
) -> None:
    statement = insert(BookEmbedding).values(
        [
            {
                "library_id": item.library_id,
                "library_book_id": item.library_book_id,
                "model_name": model_name,
                "text_version": TEXT_VERSION,
                "embedding": vector,
                "content_hash": item.hash,
            }
            for item, vector in zip(pending, vectors, strict=True)
        ]
    )
    await session.execute(
        statement.on_conflict_do_update(
            constraint="uq_book_embeddings_library_book_model_version",
            set_={
                "embedding": statement.excluded.embedding,
                "content_hash": statement.excluded.content_hash,
                "updated_at": func.now(),
            },
        )
    )


async def run_embedding(
    session: AsyncSession,
    embedder: Embedder,
    *,
    full: bool,
    library_id: int | None = None,
    batch_size: int,
    on_progress: Callable[[EmbeddingRun], None] | None = None,
) -> EmbeddingRun:
    """대상 도서를 배치로 인코딩해 저장한다.

    full이면 모두 다시 인코딩하고, 아니면 벡터가 없거나 텍스트 해시가 달라진 도서만 인코딩한다.
    인코더가 실패하면 그 자리에서 멈추고 `stopped`에 이유를 담는다. 끝난 배치는 저장돼 있다.
    """
    targets = _target_ids(library_id)
    run = EmbeddingRun(
        targets=await session.scalar(select(func.count()).select_from(targets.subquery())) or 0
    )
    last_id = 0
    while True:
        books = (
            await session.scalars(
                select(LibraryBook)
                .where(LibraryBook.id.in_(targets), LibraryBook.id > last_id)
                .order_by(LibraryBook.id)
                .limit(batch_size)
                .execution_options(populate_existing=True)
            )
        ).all()
        if not books:
            break
        last_id = books[-1].id
        items = [
            _Pending(book.library_id, book.id, text, content_hash(text))
            for book in books
            for text in [build_embedding_text(book)]
        ]
        stored = {} if full else await _stored_hashes(session, embedder.name, [b.id for b in books])
        pending = [item for item in items if stored.get(item.library_book_id) != item.hash]
        await session.commit()  # 인코딩 호출 동안 트랜잭션을 잡지 않는다

        if pending:
            try:
                vectors = await embedder.encode_documents([item.text for item in pending])
                if len(vectors) != len(pending):
                    raise EmbeddingError(EmbeddingFailure.BAD_RESPONSE, "벡터 수가 입력과 다릅니다")
            except EmbeddingError as exc:
                run.stopped = exc
                return run
            await _save(session, embedder.name, pending, vectors)
            await session.commit()
        run.encoded += len(pending)
        run.skipped += len(items) - len(pending)
        if on_progress is not None:
            on_progress(run)
    return run


async def similar_books(
    session: AsyncSession,
    embedder: Embedder,
    *,
    library_id: int,
    query: str,
    limit: int = SIMILAR_LIMIT,
) -> list[SimilarBook]:
    """질의와 코사인 유사도가 높은 그 기관의 추천 가능한 책.

    조회에 쓴 인코더의 모델 이름과 현재 텍스트 버전의 벡터만 비교한다.
    """
    vector = (await embedder.encode_queries([query]))[0]
    distance = BookEmbedding.embedding.cosine_distance(vector)
    rows = await session.execute(
        select(LibraryBook, (1 - distance).label("similarity"))
        .join(
            BookEmbedding,
            and_(
                BookEmbedding.library_id == LibraryBook.library_id,
                BookEmbedding.library_book_id == LibraryBook.id,
            ),
        )
        .where(
            BookEmbedding.library_id == library_id,
            BookEmbedding.model_name == embedder.name,
            BookEmbedding.text_version == TEXT_VERSION,
            LibraryBook.id.in_(recommendable_ids(library_id)),
        )
        .order_by(distance, LibraryBook.id)
        .limit(limit)
    )
    return [SimilarBook(book, float(similarity)) for book, similarity in rows]
