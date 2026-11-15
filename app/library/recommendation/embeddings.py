"""기관 도서 벡터의 적재와 두 층 유사도 조회.

책 하나는 한 층에만 속한다. 공식 서지에 연결된 책은 공식 서지 벡터
(`app/central/official_embeddings.py`)를, 연결되지 않은 책(ISBN 없음, 못 찾음)은 여기서 만드는
기관 도서 벡터를 쓴다. 기관 도서 벡터의 대상은
연결되지 않은 추천 가능한 기관 도서다(`search.py`의 추천 가능 조건). 배치 흐름은 운영자 층의
`run_layer`와 같다. 텍스트 원문은 저장하지 않는다. 벡터, 모델 이름, 텍스트 버전, 종류, 해시만 둔다.
"""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Select, and_, func, select, union_all
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.embedding import (
    Embedder,
    EmbeddingRun,
    PendingText,
    run_layer,
    upsert_vectors,
)
from app.central.models import Book, OfficialBookEmbedding
from app.core import embedding_text as rules
from app.core.embedding_text import TextKind, content_hash
from app.library.models.catalog import Holding, LibraryBook
from app.library.models.embedding import BookEmbedding
from app.library.recommendation.embedding_text import library_embedding_text
from app.library.recommendation.search import RECOMMENDABLE_STATUSES, recommendable_ids

SIMILAR_LIMIT = 5


@dataclass(frozen=True)
class SimilarBook:
    library_book: LibraryBook
    similarity: float  # 코사인 유사도


def _recommendable(library_id: int | None) -> Select:
    """추천 가능한 기관 도서 id. 기관을 주지 않는 것은 운영자 실행뿐이다."""
    if library_id is not None:
        return recommendable_ids(library_id)
    return (
        select(Holding.library_book_id).where(Holding.status.in_(RECOMMENDABLE_STATUSES)).distinct()
    )


def held_official_ids(library_id: int) -> Select:
    """그 기관의 추천 가능한 책에 연결된 공식 서지 id. 기관을 지정한 공식 서지 벡터 적재에 쓴다."""
    return (
        select(LibraryBook.book_id)
        .where(
            LibraryBook.library_id == library_id,
            LibraryBook.id.in_(recommendable_ids(library_id)),
            LibraryBook.book_id.is_not(None),
        )
        .distinct()
    )


@dataclass(frozen=True)
class _LibraryLayer:
    model_name: str
    kind: TextKind
    text_version: int
    library_id: int | None

    def _targets(self) -> Select:
        return select(LibraryBook.id).where(
            LibraryBook.id.in_(_recommendable(self.library_id)), LibraryBook.book_id.is_(None)
        )

    async def count(self, session: AsyncSession) -> int:
        return await session.scalar(select(func.count()).select_from(self._targets().subquery()))

    async def read(self, session: AsyncSession, after_id: int, limit: int) -> list[PendingText]:
        books = (
            await session.scalars(
                select(LibraryBook)
                .where(LibraryBook.id.in_(self._targets()), LibraryBook.id > after_id)
                .order_by(LibraryBook.id)
                .limit(limit)
                .execution_options(populate_existing=True)
            )
        ).all()
        return [
            PendingText(
                book.id,
                text,
                content_hash(text),
                {"library_id": book.library_id, "library_book_id": book.id},
            )
            for book in books
            for text in [library_embedding_text(book, self.kind)]
        ]

    async def stored_hashes(self, session: AsyncSession, ids: list[int]) -> dict[int, str]:
        rows = await session.execute(
            select(BookEmbedding.library_book_id, BookEmbedding.content_hash).where(
                BookEmbedding.library_book_id.in_(ids),
                BookEmbedding.model_name == self.model_name,
                BookEmbedding.text_version == self.text_version,
                BookEmbedding.kind == self.kind,
            )
        )
        return {target: stored for target, stored in rows}

    async def save(
        self, session: AsyncSession, pending: list[PendingText], vectors: list[list[float]]
    ) -> None:
        await upsert_vectors(
            session,
            BookEmbedding,
            constraint="uq_book_embeddings_library_book_model_version_kind",
            values={
                "model_name": self.model_name,
                "text_version": self.text_version,
                "kind": self.kind.value,
            },
            pending=pending,
            vectors=vectors,
        )


async def run_library_embedding(
    session: AsyncSession,
    embedder: Embedder,
    *,
    full: bool,
    batch_size: int | None = None,
    kind: TextKind = TextKind.FULL,
    library_id: int | None = None,
    on_progress: Callable[[EmbeddingRun], None] | None = None,
) -> EmbeddingRun:
    """공식 서지에 연결되지 않은 추천 가능한 기관 도서의 벡터를 적재한다."""
    layer = _LibraryLayer(embedder.name, TextKind(kind), rules.TEXT_VERSION, library_id)
    return await run_layer(
        session, embedder, layer, full=full, batch_size=batch_size, on_progress=on_progress
    )


async def missing_official_descriptions(session: AsyncSession) -> tuple[int, int]:
    """(공식 소개 없는 공식 서지 수, 그중 연결된 기관 도서에 소개가 있는 수). 적재 출력용."""
    blank = func.coalesce(func.btrim(Book.description), "") == ""
    total = await session.scalar(select(func.count()).select_from(Book).where(blank))
    with_own = await session.scalar(
        select(func.count(func.distinct(Book.id)))
        .join(LibraryBook, LibraryBook.book_id == Book.id)
        .where(blank, func.coalesce(func.btrim(LibraryBook.description), "") != "")
    )
    return total or 0, with_own or 0


async def similar_books(
    session: AsyncSession,
    embedder: Embedder,
    *,
    library_id: int,
    query: str,
    limit: int = SIMILAR_LIMIT,
    kind: TextKind = TextKind.FULL,
) -> list[SimilarBook]:
    """질의와 코사인 유사도가 높은 그 기관의 추천 가능한 책.

    연결된 책은 공식 서지 벡터로, 연결되지 않은 책은 기관 도서 벡터로 비교해 한 순위로 합친다.
    조회에 쓴 인코더의 모델 이름, 현재 텍스트 버전, 종류의 벡터만 비교한다. 공식 서지 벡터가
    결과에 오르는 길은 이 기관의 추천 가능한 기관 도서가 그 공식 서지를 가리키는 것뿐이다.
    """
    vector = (await embedder.encode_queries([query]))[0]
    kind = TextKind(kind)
    recommendable = LibraryBook.id.in_(recommendable_ids(library_id))
    official_distance = OfficialBookEmbedding.embedding.cosine_distance(vector)
    own_distance = BookEmbedding.embedding.cosine_distance(vector)
    linked = (
        select(LibraryBook.id.label("library_book_id"), official_distance.label("distance"))
        .join(OfficialBookEmbedding, OfficialBookEmbedding.book_id == LibraryBook.book_id)
        .where(
            LibraryBook.library_id == library_id,
            recommendable,
            OfficialBookEmbedding.model_name == embedder.name,
            OfficialBookEmbedding.text_version == rules.TEXT_VERSION,
            OfficialBookEmbedding.kind == kind,
        )
    )
    own = (
        select(LibraryBook.id.label("library_book_id"), own_distance.label("distance"))
        .join(
            BookEmbedding,
            and_(
                BookEmbedding.library_id == LibraryBook.library_id,
                BookEmbedding.library_book_id == LibraryBook.id,
            ),
        )
        .where(
            LibraryBook.library_id == library_id,
            LibraryBook.book_id.is_(None),
            recommendable,
            BookEmbedding.library_id == library_id,
            BookEmbedding.model_name == embedder.name,
            BookEmbedding.text_version == rules.TEXT_VERSION,
            BookEmbedding.kind == kind,
        )
    )
    ranked = union_all(linked, own).subquery()
    rows = await session.execute(
        select(LibraryBook, (1 - ranked.c.distance).label("similarity"))
        .join(ranked, ranked.c.library_book_id == LibraryBook.id)
        .order_by(ranked.c.distance, LibraryBook.id)
        .limit(limit)
    )
    return [SimilarBook(book, float(similarity)) for book, similarity in rows]
