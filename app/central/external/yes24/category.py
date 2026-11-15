"""CATEGORY API 역할 함수. 실험 장서 받기(`evals/collection/fetch.py`) 전용이다.

서비스 경로에서 부르지 않는다. YES24 이용 조건의 "소장 도서의 ISBN만 조회한다"는 규칙의 예외이고,
한 번만 받는다.
"""

from typing import Any

from app.central.external.yes24.client import StopReason, Yes24Client, Yes24Stopped
from app.central.external.yes24.definitions import (
    CATEGORY_STEADY_SELLERS,
    DETAIL_ALL,
    ITEMS_KEY,
    MAX_PAGE_SIZE,
    TOTAL_COUNT_KEY,
)


async def steady_sellers(
    client: Yes24Client, category_id: str, *, page: int = 1, page_size: int = MAX_PAGE_SIZE
) -> tuple[list[dict[str, Any]], int]:
    """카테고리의 스테디셀러 한 쪽을 상세 정보와 함께 받는다. (원본 상품 목록, 전체 수).

    원본을 돌려주는 것은 받은 값을 파일에 그대로 남기기 위해서다. 결과가 없으면 빈 목록이다.
    """
    data = await client.get(
        CATEGORY_STEADY_SELLERS,
        {
            "categoryId": category_id,
            "page": str(page),
            "pageSize": str(page_size),
            "detail": DETAIL_ALL,
        },
    )
    if data is None:
        return [], 0
    items = data.get(ITEMS_KEY)
    if not isinstance(items, list):
        raise Yes24Stopped(StopReason.UPSTREAM_UNAVAILABLE)
    total = data.get(TOTAL_COUNT_KEY)
    return [item for item in items if isinstance(item, dict)], total if isinstance(
        total, int
    ) else 0
