"""운영자 층의 채움 접점을 기관 도서로 구현한다. 기관의 처리 현황도 여기서 센다.

연결은 공식 서지 참조와 처리 상태만 쓴다. 훅을 부르지 않으므로 기관 개별 기능의 값은 바뀌지 않는다.
"""

from sqlalchemy import exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.enrichment import LookupOutcome
from app.central.models import Book
from app.core import clock
from app.library.models.catalog import EnrichmentStatus, Holding, HoldingStatus, LibraryBook
from app.library.schemas.catalog import EnrichmentCounts
from app.library.services.library_books import connect_official

FAILED_STATUSES = (EnrichmentStatus.NOT_FOUND, EnrichmentStatus.MISMATCH)

_HELD = exists().where(
    Holding.library_book_id == LibraryBook.id, Holding.status != HoldingStatus.WITHDRAWN
)


def _held_isbns(*statuses: EnrichmentStatus):
    return (
        select(LibraryBook.isbn)
        .where(LibraryBook.isbn.is_not(None), LibraryBook.enrichment_status.in_(statuses), _HELD)
        .distinct()
    )


class LibraryEnrichmentTargets:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def isbns(self, limit: int, retry_failed: bool) -> list[str]:
        query = _held_isbns(EnrichmentStatus.PENDING).order_by(LibraryBook.isbn).limit(limit)
        isbns = list(await self._session.scalars(query))
        if retry_failed and len(isbns) < limit:
            failed = await self._session.scalars(
                _held_isbns(*FAILED_STATUSES)
                .where(LibraryBook.isbn.not_in(isbns))
                .order_by(LibraryBook.isbn)
                .limit(limit - len(isbns))
            )
            isbns += list(failed)
        return isbns

    async def remaining(self) -> int:
        pending = _held_isbns(EnrichmentStatus.PENDING).subquery()
        return await self._session.scalar(select(func.count()).select_from(pending)) or 0

    async def link(self, isbn: str, book: Book) -> None:
        """같은 ISBN의 기관 도서를 모두 연결한다. 수정과 겹치지 않게 잠그고 다시 읽는다."""
        library_books = await self._session.scalars(
            select(LibraryBook)
            .where(LibraryBook.isbn == isbn)
            .with_for_update(of=LibraryBook)
            .execution_options(populate_existing=True)
        )
        now = clock.now()
        for library_book in library_books:
            connect_official(library_book, book)
            library_book.enrichment_checked_at = now

    async def mark(self, isbn: str, outcome: LookupOutcome) -> None:
        await self._session.execute(
            update(LibraryBook)
            .where(LibraryBook.isbn == isbn, LibraryBook.book_id.is_(None))
            .values(enrichment_status=EnrichmentStatus(outcome), enrichment_checked_at=clock.now())
        )


async def enrichment_counts(session: AsyncSession, library_id: int) -> EnrichmentCounts:
    """로그인한 기관의 소장 도서를 처리 상태별로 센다. ISBN 없는 도서는 따로 센다."""
    own = (LibraryBook.library_id == library_id, _HELD)
    rows = await session.execute(
        select(LibraryBook.enrichment_status, func.count())
        .where(*own, LibraryBook.isbn.is_not(None))
        .group_by(LibraryBook.enrichment_status)
    )
    no_isbn = await session.scalar(
        select(func.count()).select_from(LibraryBook).where(*own, LibraryBook.isbn.is_(None))
    )
    counts = {status.value: count for status, count in rows.all()}
    return EnrichmentCounts(**counts, no_isbn=no_isbn or 0)
