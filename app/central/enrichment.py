"""운영자 층의 서지정보 채움. 소장 도서의 ISBN으로 공식 서지를 만든다.

기관 모델을 모른다. 대상 조회와 연결 처리는 EnrichmentTargets가 맡고, 실행하는 쪽이 넘겨준다.
외부 호출 동안 트랜잭션을 잡지 않고, ISBN마다 커밋해서 중단돼도 처리한 결과가 남는다.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.external.yes24.client import StopReason, Yes24Client, Yes24Stopped
from app.central.external.yes24.goods import get_items_by_isbn
from app.central.external.yes24.parsing import Yes24Item
from app.central.models import Book, ExternalSource

DEFAULT_LIMIT = 100


class LookupOutcome(StrEnum):
    NOT_FOUND = "not_found"
    MISMATCH = "mismatch"


class EnrichmentTargets(Protocol):
    """채움 대상을 아는 쪽이 구현한다. 커밋은 실행이 맡는다."""

    async def isbns(self, limit: int, retry_failed: bool) -> list[str]:
        """처리할 ISBN. 처리 대기를 먼저, retry_failed면 찾지 못한 ISBN을 그 뒤에 둔다."""
        ...

    async def remaining(self) -> int:
        """남은 처리 대기 ISBN 수."""
        ...

    async def link(self, isbn: str, book: Book) -> None:
        """그 ISBN을 공식 서지에 연결한다."""
        ...

    async def mark(self, isbn: str, outcome: LookupOutcome) -> None:
        """공식 서지를 만들지 못한 결과를 남긴다."""
        ...


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


async def _process(
    session: AsyncSession,
    client: Yes24Client,
    targets: EnrichmentTargets,
    isbn: str,
    result: EnrichmentResult,
) -> None:
    book = await _find_official(session, isbn)
    await session.commit()  # 외부 호출 전에 트랜잭션을 끝낸다
    if book is not None:
        await targets.link(isbn, book)
        result.linked += 1
        return

    items = await get_items_by_isbn(client, isbn)
    item = next((i for i in items if i.isbn13 == isbn), None)
    if items and item is None:
        await targets.mark(isbn, LookupOutcome.MISMATCH)
        result.mismatch += 1
    elif item is None or not item.title or not item.author:
        # 서명·저자는 필수다. 기관 값으로 채우지 않고 공식 서지를 만들지 않는다.
        await targets.mark(isbn, LookupOutcome.NOT_FOUND)
        result.not_found += 1
    else:
        await targets.link(isbn, await _create_official(session, isbn, item))
        result.enriched += 1


async def run_enrichment(
    session: AsyncSession,
    client: Yes24Client,
    targets: EnrichmentTargets,
    *,
    limit: int = DEFAULT_LIMIT,
    retry_failed: bool = False,
) -> EnrichmentResult:
    """대상 ISBN을 하나씩 처리한다. 외부 장애가 나면 멈추고 남은 ISBN은 그대로 둔다."""
    result = EnrichmentResult()
    for isbn in await targets.isbns(limit, retry_failed):
        try:
            await _process(session, client, targets, isbn, result)
        except Yes24Stopped as exc:
            result.stopped = exc.reason
            break
        await session.commit()
    result.remaining = await targets.remaining()
    await session.commit()
    return result
