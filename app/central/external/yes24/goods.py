"""GOODS API 역할 함수."""

from typing import Any

from app.central.external.yes24.client import StopReason, Yes24Client, Yes24Stopped
from app.central.external.yes24.definitions import (
    DETAIL_ALL,
    GOODS_ITEM_DETAIL,
    GOODS_ITEM_LIST,
    SEARCH_CATEGORY_BOOK,
    SEARCH_TYPE_ISBN13,
)
from app.central.external.yes24.parsing import Yes24Item, parse_item


async def get_items_by_isbn(client: Yes24Client, isbn: str) -> list[Yes24Item]:
    """ISBN13으로 상품 상세 정보를 조회한다. 찾지 못하면 빈 목록이다."""
    data = await client.get(
        GOODS_ITEM_DETAIL, {"searchType": SEARCH_TYPE_ISBN13, "query": isbn, "detail": DETAIL_ALL}
    )
    return _items(data)


async def search_items(client: Yes24Client, query: str, page_size: int) -> list[Yes24Item]:
    """검색어로 도서를 찾는다. 평가 표본 전용이고 서비스 경로에서 부르지 않는다."""
    data = await client.get(
        GOODS_ITEM_LIST,
        {
            "query": query,
            "category": SEARCH_CATEGORY_BOOK,
            "pageSize": str(page_size),
            "detail": DETAIL_ALL,
        },
    )
    return _items(data)


def _items(data: dict[str, Any] | None) -> list[Yes24Item]:
    if data is None:
        return []
    items = data.get("items")
    if not isinstance(items, list):
        raise Yes24Stopped(StopReason.UPSTREAM_UNAVAILABLE)
    return [parse_item(item) for item in items if isinstance(item, dict)]
