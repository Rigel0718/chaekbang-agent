"""구매 요청서 테스트 도구: 가짜 정가 조회기와 요청서·신청 만들기. 실제 YES24는 부르지 않는다."""

from collections.abc import Awaitable, Callable, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.central.external.yes24.client import StopReason
from app.central.list_prices import PriceLookupUnavailable
from app.core.text import match_key
from tests.helpers import insert


class FakeListPrices:
    """ISBN별 정가를 정해 두고 호출을 기록한다. 정하지 않은 ISBN은 가격 없음이다.

    `during`은 조회하는 동안(승인의 읽기와 기록 사이) 끼어드는 일을 흉내 낼 때 쓴다.
    """

    def __init__(self, prices: dict[str, int | None] | None = None) -> None:
        self.prices: dict[str, int | None] = dict(prices or {})
        self.unavailable = False
        self.calls: list[list[str]] = []
        self.during: Callable[[], Awaitable[None]] | None = None

    async def lookup(self, isbns: Sequence[str]) -> dict[str, int | None]:
        self.calls.append(list(isbns))
        if self.during is not None:
            during, self.during = self.during, None
            await during()
        if self.unavailable:
            raise PriceLookupUnavailable(StopReason.UPSTREAM_UNAVAILABLE)
        return {isbn: self.prices.get(isbn) for isbn in dict.fromkeys(isbns)}


def item_body(isbn: str, quantity: int = 1, **overrides) -> dict:
    return {
        "isbn": isbn,
        "title": f"책 {isbn[-4:]}",
        "author": "저자",
        "quantity": quantity,
        "reason_kind": "manual",
        **overrides,
    }


def request_body(items: list[dict], **overrides) -> dict:
    return {"title": "12월 보충 구매", "items": items, **overrides}


async def add_book_request(
    session: AsyncSession,
    library_id: int,
    *,
    member_id: int | None,
    title: str = "작별하지 않는다",
    isbn: str | None = None,
    status: str = "requested",
) -> dict:
    return dict(
        await insert(
            session,
            "book_requests",
            library_id=library_id,
            member_id=member_id,
            title=title,
            title_key=match_key(title),
            isbn=isbn,
            status=status,
        )
    )
