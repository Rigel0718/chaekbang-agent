"""공식 서지 벡터의 적재. 대상은 공식 서지 전부이고 공식 값만으로 텍스트를 만든다.

운영자 층이라 기관을 모른다. 기관을 지정한 실행은 부르는 쪽이 공식 서지 id 조건(`within`)을
넘긴다. 같은 공식 서지를 가진 기관이 몇이든 한 번만 인코딩한다.
"""

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.embedding import (
    Embedder,
    EmbeddingRun,
    PendingText,
    run_layer,
    upsert_vectors,
)
from app.central.embedding_text import official_embedding_text
from app.central.models import Book, OfficialBookEmbedding
from app.core import embedding_text as rules
from app.core.embedding_text import TextKind, content_hash


@dataclass(frozen=True)
class _OfficialLayer:
    model_name: str
    kind: TextKind
    text_version: int
    within: Select | None

    def _targets(self) -> Select:
        statement = select(Book.id)
        if self.within is not None:
            statement = statement.where(Book.id.in_(self.within))
        return statement

    async def count(self, session: AsyncSession) -> int:
        return await session.scalar(select(func.count()).select_from(self._targets().subquery()))

    async def read(self, session: AsyncSession, after_id: int, limit: int) -> list[PendingText]:
        books = (
            await session.scalars(
                select(Book)
                .where(Book.id.in_(self._targets()), Book.id > after_id)
                .order_by(Book.id)
                .limit(limit)
                .execution_options(populate_existing=True)
            )
        ).all()
        return [
            PendingText(book.id, text, content_hash(text), {"book_id": book.id})
            for book in books
            for text in [official_embedding_text(book, self.kind)]
        ]

    async def stored_hashes(self, session: AsyncSession, ids: list[int]) -> dict[int, str]:
        rows = await session.execute(
            select(OfficialBookEmbedding.book_id, OfficialBookEmbedding.content_hash).where(
                OfficialBookEmbedding.book_id.in_(ids),
                OfficialBookEmbedding.model_name == self.model_name,
                OfficialBookEmbedding.text_version == self.text_version,
                OfficialBookEmbedding.kind == self.kind,
            )
        )
        return {target: stored for target, stored in rows}

    async def save(
        self, session: AsyncSession, pending: list[PendingText], vectors: list[list[float]]
    ) -> None:
        await upsert_vectors(
            session,
            OfficialBookEmbedding,
            constraint="uq_official_book_embeddings_book_model_version_kind",
            values={
                "model_name": self.model_name,
                "text_version": self.text_version,
                "kind": self.kind.value,
            },
            pending=pending,
            vectors=vectors,
        )


async def run_official_embedding(
    session: AsyncSession,
    embedder: Embedder,
    *,
    full: bool,
    batch_size: int | None = None,
    kind: TextKind = TextKind.FULL,
    within: Select | None = None,
    on_progress: Callable[[EmbeddingRun], None] | None = None,
) -> EmbeddingRun:
    """공식 서지 벡터를 적재한다.

    within은 대상 공식 서지 id를 좁히는 조건이다(공식 서지 id 열 하나를 고르는 select).
    """
    layer = _OfficialLayer(embedder.name, TextKind(kind), rules.TEXT_VERSION, within)
    return await run_layer(
        session, embedder, layer, full=full, batch_size=batch_size, on_progress=on_progress
    )
