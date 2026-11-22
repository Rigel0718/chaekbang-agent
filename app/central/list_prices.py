"""구매 요청서의 정가 조회: 접점 `ListPriceLookup`과 YES24 구현.

정가는 예산 추정과 공적 보고용 기록이라 요청서 상세와 승인 때 실시간으로 조회하고, 조회한 값은
요청서가 확정될 때의 기록 말고는 저장하지 않는다. 읽는 값은 같은 ISBN13 상품의 정가(`shopPrice`)
하나다. 판매가, 판매 상태, 응답 원본은 읽지도 내보내지도 않는다(YES24 이용 조건).

조회기는 서비스 중 쓰는 호출이라 서버가 처음 쓸 때 만든다(`app/library/api/purchase_requests.py`).
호출 간격은 조회기 하나가 공유하고, 여러 요청이 겹치면 줄을 서서 차례로 부른다.
"""

import asyncio
from collections.abc import Sequence
from typing import Protocol

from app.central.external.yes24.client import StopReason, Yes24Client, Yes24Stopped
from app.central.external.yes24.goods import get_items_by_isbn
from app.central.external.yes24.parsing import Yes24Item


class PriceLookupUnavailable(Exception):
    """정가 조회를 쓸 수 없다(외부 장애, 한도 초과, 키 없음). 사유만 담는다."""

    def __init__(self, reason: StopReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


class ListPriceLookup(Protocol):
    async def lookup(self, isbns: Sequence[str]) -> dict[str, int | None]:
        """ISBN마다 정가(원, int)를 돌려준다. 정가를 찾지 못한 ISBN의 값은 None이다.

        조회를 쓸 수 없으면 `PriceLookupUnavailable`이다. 부분 결과는 돌려주지 않는다.
        """
        ...


def _list_price(items: list[Yes24Item], isbn: str) -> int | None:
    """요청한 ISBN과 같은 ISBN13 상품의 정가. 0이나 없음은 None이다."""
    for item in items:
        if item.isbn13 == isbn and item.list_price is not None and item.list_price > 0:
            return item.list_price
    return None


class Yes24ListPrices:
    """YES24 상품 상세(`itemDetail`)로 ISBN마다 정가를 조회한다."""

    def __init__(self, client: Yes24Client) -> None:
        self._client = client
        self._lock = asyncio.Lock()

    async def lookup(self, isbns: Sequence[str]) -> dict[str, int | None]:
        prices: dict[str, int | None] = {}
        async with self._lock:
            for isbn in dict.fromkeys(isbns):
                try:
                    items = await get_items_by_isbn(self._client, isbn)
                except Yes24Stopped as stopped:
                    raise PriceLookupUnavailable(stopped.reason) from None
                prices[isbn] = _list_price(items, isbn)
        return prices


class UnconfiguredListPrices:
    """YES24 키가 없을 때의 조회기. 항상 쓸 수 없다고 답한다(서버는 키 없이도 시작한다)."""

    async def lookup(self, isbns: Sequence[str]) -> dict[str, int | None]:
        raise PriceLookupUnavailable(StopReason.AUTH_FAILED)
