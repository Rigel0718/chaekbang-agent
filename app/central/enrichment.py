"""운영자 층의 서지정보 채움. 소장 도서의 ISBN으로 공식 서지를 만든다.

기관 모델을 모른다. 대상 조회와 연결 처리는 EnrichmentTargets가 맡고, 실행하는 쪽이 넘겨준다.
외부 호출 동안 트랜잭션을 잡지 않고, ISBN마다 커밋해서 중단돼도 처리한 결과가 남는다.

출처는 정보나루, 카카오, YES24다. ISBN마다 셋을 한 번씩 부르고 필드별 기준 출처로 합친다
(`sources.merge`).
어느 출처든 멈춰야 하는 오류가 나면 실행을 멈춘다. 한 출처 없이 만들면 이미 있는 공식 서지는
고치지 않는 규칙 때문에 그 값(예: 정보나루의 KDC·부가기호)을 나중에 채울 수 없어서다.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.central.external.data4library.client import Data4LibraryClient, get_books_by_isbn
from app.central.external.http import SourceStopped, StopReason
from app.central.external.kakao.client import KakaoClient, get_documents_by_isbn
from app.central.external.yes24.client import Yes24Client
from app.central.external.yes24.goods import get_items_by_isbn
from app.central.models import Book
from app.central.official_books import create_official, find_official
from app.central.sources import LookupOutcome, OfficialValues, merge

__all__ = [
    "DEFAULT_LIMIT",
    "EnrichmentResult",
    "EnrichmentTargets",
    "Lookup",
    "LookupOutcome",
    "lookup_sources",
    "run_enrichment",
]

DEFAULT_LIMIT = 100

# ISBN 하나의 외부 조회. 공식 서지 값이나, 만들지 못한 이유를 돌려준다. 멈춰야 하면 SourceStopped다.
Lookup = Callable[[str], Awaitable[OfficialValues | LookupOutcome]]


def lookup_sources(
    data4library: Data4LibraryClient, kakao: KakaoClient, yes24: Yes24Client
) -> Lookup:
    """정보나루, 카카오, YES24를 한 번씩 불러 합치는 조회."""

    async def lookup(isbn: str) -> OfficialValues | LookupOutcome:
        books = await get_books_by_isbn(data4library, isbn)
        documents = await get_documents_by_isbn(kakao, isbn)
        items = await get_items_by_isbn(yes24, isbn)
        return merge(isbn, books, documents, items)

    return lookup


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
    stopped_source: str | None = None  # 멈추게 한 출처 이름

    @property
    def processed(self) -> int:
        return self.linked + self.enriched + self.not_found + self.mismatch


async def _process(
    session: AsyncSession,
    lookup: Lookup,
    targets: EnrichmentTargets,
    isbn: str,
    result: EnrichmentResult,
) -> None:
    book = await find_official(session, isbn)
    await session.commit()  # 외부 호출 전에 트랜잭션을 끝낸다
    if book is not None:
        await targets.link(isbn, book)
        result.linked += 1
        return

    found = await lookup(isbn)
    if found is LookupOutcome.MISMATCH:
        await targets.mark(isbn, LookupOutcome.MISMATCH)
        result.mismatch += 1
    elif isinstance(found, LookupOutcome):
        # 서명·저자는 필수다. 기관 값으로 채우지 않고 공식 서지를 만들지 않는다.
        await targets.mark(isbn, LookupOutcome.NOT_FOUND)
        result.not_found += 1
    else:
        await targets.link(isbn, await create_official(session, isbn, found))
        result.enriched += 1


async def run_enrichment(
    session: AsyncSession,
    lookup: Lookup,
    targets: EnrichmentTargets,
    *,
    limit: int = DEFAULT_LIMIT,
    retry_failed: bool = False,
) -> EnrichmentResult:
    """대상 ISBN을 하나씩 처리한다. 외부 장애가 나면 멈추고 남은 ISBN은 그대로 둔다."""
    result = EnrichmentResult()
    for isbn in await targets.isbns(limit, retry_failed):
        try:
            await _process(session, lookup, targets, isbn, result)
        except SourceStopped as exc:
            result.stopped = exc.reason
            result.stopped_source = exc.source
            break
        await session.commit()
    result.remaining = await targets.remaining()
    await session.commit()
    return result
