"""운영자 층의 서지정보 채움. 소장 도서의 ISBN으로 공식 서지를 만들고 기관 도서를 연결한다.

공식 서지 참조와 처리 상태만 쓴다. 기관이 정한 값은 건드리지 않는다.
외부 호출 동안 트랜잭션을 잡지 않고, ISBN마다 커밋해서 중단돼도 처리한 결과가 남는다.
"""

from dataclasses import dataclass

from sqlalchemy import exists, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.external.yes24.client import StopReason, Yes24Client, Yes24Stopped
from app.external.yes24.goods import get_items_by_isbn
from app.external.yes24.parsing import Yes24Item
from app.models.catalog import (
    Book,
    EnrichmentStatus,
    ExternalSource,
    Holding,
    HoldingStatus,
    LibraryBook,
)
from app.schemas.catalog import EnrichmentCounts
from app.services.library_books import connect_official

DEFAULT_LIMIT = 100
FAILED_STATUSES = (EnrichmentStatus.NOT_FOUND, EnrichmentStatus.MISMATCH)

_HELD = exists().where(
    Holding.library_book_id == LibraryBook.id, Holding.status != HoldingStatus.WITHDRAWN
)


@dataclass
class EnrichmentResult:
    linked: int = 0  # 이미 있는 공식 서지에 연결
    enriched: int = 0  # 공식 서지를 새로 만듦
    not_found: int = 0
    mismatch: int = 0
    remaining: int = 0  # 남은 처리 대기 ISBN
    stopped: StopReason | None = None

    @property
    def processed(self) -> int:
        return self.linked + self.enriched + self.not_found + self.mismatch


def _held_isbns(*statuses: EnrichmentStatus):
    return (
        select(LibraryBook.isbn)
        .where(LibraryBook.isbn.is_not(None), LibraryBook.enrichment_status.in_(statuses), _HELD)
        .distinct()
    )


async def _target_isbns(session: AsyncSession, limit: int, retry_failed: bool) -> list[str]:
    """처리 대기 ISBN을 먼저, retry_failed면 찾지 못한 ISBN을 그 뒤에 둔다."""
    query = _held_isbns(EnrichmentStatus.PENDING).order_by(LibraryBook.isbn).limit(limit)
    isbns = list(await session.scalars(query))
    if retry_failed and len(isbns) < limit:
        failed = await session.scalars(
            _held_isbns(*FAILED_STATUSES)
            .where(LibraryBook.isbn.not_in(isbns))
            .order_by(LibraryBook.isbn)
            .limit(limit - len(isbns))
        )
        isbns += list(failed)
    return isbns


async def _find_official(session: AsyncSession, isbn: str) -> Book | None:
    return await session.scalar(select(Book).where(Book.isbn == isbn))


async def _create_official(session: AsyncSession, isbn: str, item: Yes24Item) -> Book:
    await session.execute(
        insert(Book)
        .values(
            isbn=isbn,
            title=item.title,
            author=item.author,
            publisher=item.publisher,
            published_date=item.published_date,
            list_price=item.list_price,
            cover_url=item.cover_url,
            description=item.description,
            subtitle=item.subtitle,
            table_of_contents=item.table_of_contents,
            series_name=item.series_name,
            external_source=ExternalSource.YES24,
            external_url=item.url,
            external_category=item.category,
        )
        .on_conflict_do_nothing(index_elements=["isbn"])
    )
    book = await _find_official(session, isbn)
    assert book is not None
    return book


async def _link_all(session: AsyncSession, isbn: str, book: Book) -> None:
    """같은 ISBN의 기관 도서를 모두 연결한다. 그 사이의 수정과 겹치지 않게 잠그고 다시 읽는다."""
    library_books = await session.scalars(
        select(LibraryBook)
        .where(LibraryBook.isbn == isbn)
        .with_for_update(of=LibraryBook)
        .execution_options(populate_existing=True)
    )
    now = clock.now()
    for library_book in library_books:
        connect_official(library_book, book)
        library_book.enrichment_checked_at = now


async def _mark(session: AsyncSession, isbn: str, status: EnrichmentStatus) -> None:
    await session.execute(
        update(LibraryBook)
        .where(LibraryBook.isbn == isbn, LibraryBook.book_id.is_(None))
        .values(enrichment_status=status, enrichment_checked_at=clock.now())
    )


async def _process(
    session: AsyncSession, client: Yes24Client, isbn: str, result: EnrichmentResult
) -> None:
    book = await _find_official(session, isbn)
    await session.commit()  # 외부 호출 전에 트랜잭션을 끝낸다
    if book is not None:
        await _link_all(session, isbn, book)
        result.linked += 1
        return

    items = await get_items_by_isbn(client, isbn)
    item = next((i for i in items if i.isbn13 == isbn), None)
    if items and item is None:
        await _mark(session, isbn, EnrichmentStatus.MISMATCH)
        result.mismatch += 1
    elif item is None or not item.title or not item.author:
        # 서명·저자는 필수다. 기관 값으로 채우지 않고 공식 서지를 만들지 않는다.
        await _mark(session, isbn, EnrichmentStatus.NOT_FOUND)
        result.not_found += 1
    else:
        await _link_all(session, isbn, await _create_official(session, isbn, item))
        result.enriched += 1


async def run_enrichment(
    session: AsyncSession,
    client: Yes24Client,
    *,
    limit: int = DEFAULT_LIMIT,
    retry_failed: bool = False,
) -> EnrichmentResult:
    """대상 ISBN을 하나씩 처리한다. 외부 장애가 나면 멈추고 남은 ISBN은 그대로 둔다."""
    result = EnrichmentResult()
    for isbn in await _target_isbns(session, limit, retry_failed):
        try:
            await _process(session, client, isbn, result)
        except Yes24Stopped as exc:
            result.stopped = exc.reason
            break
        await session.commit()
    pending = _held_isbns(EnrichmentStatus.PENDING).subquery()
    result.remaining = await session.scalar(select(func.count()).select_from(pending)) or 0
    await session.commit()
    return result


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
