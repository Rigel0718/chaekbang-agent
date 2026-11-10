"""YES24 Open API 정의. 엔드포인트와 응답 필드는 여기에만 둔다.

새 엔드포인트는 Endpoint 상수로, 새 응답 필드는 ITEM_FIELDS에 한 줄로 추가한다.
근거: yes24-open-api-guide/의 문서와 실제 응답.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Endpoint:
    path: str


GOODS_ITEM_DETAIL = Endpoint("/goods/itemDetail")
GOODS_ITEM_LIST = Endpoint("/goods/itemList")

API_KEY_HEADER = "X-Api-Key"
SEARCH_TYPE_ISBN13 = "ISBN13"
SEARCH_CATEGORY_BOOK = "BOOK"
DETAIL_ALL = "Y"
REQUEST_TIMEOUT_SECONDS = 10.0
MIN_CALL_INTERVAL_SECONDS = 0.2  # 공식 한도 초당 10회의 절반


@dataclass(frozen=True)
class ItemField:
    """응답 상품에서 값을 꺼낼 경로와 저장할 수 있는 최대 길이."""

    path: tuple[str, ...]
    max_length: int | None = None


# 필드 이름은 Yes24Item의 필드 이름이다. max_length는 공식 서지의 열 길이와 같다.
ITEM_FIELDS = {
    "isbn13": ItemField(("isbn13",)),
    "title": ItemField(("title",), 500),
    "author": ItemField(("author",), 300),
    "publisher": ItemField(("publisher",), 200),
    "published_date": ItemField(("publishDate",)),
    "list_price": ItemField(("shopPrice",)),
    "introduction": ItemField(("contentDetail", "bookIntroduction")),
    "summary": ItemField(("contentDetail", "bookSummary")),
    "table_of_contents": ItemField(("contentDetail", "tableOfContents")),
    "cover_url": ItemField(("cover",), 1000),
    "subtitle": ItemField(("subTitle",), 500),
    "series": ItemField(("series",), 500),
    "url": ItemField(("link",), 1000),
    "category": ItemField(("goodsSortNm",), 100),
}
SERIES_NAME_KEY = "seriesName"

# 상품을 찾지 못한 것으로 보는 오류 코드. 404는 코드와 상관없이 찾지 못한 것이다.
NOT_FOUND_ERROR_CODES = frozenset({"GOODS_001", "GOODS_002", "SEARCH_002", "PARAM_004"})
