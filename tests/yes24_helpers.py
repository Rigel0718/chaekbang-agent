"""YES24 응답 픽스처와 가짜 서버. 실제 응답 구조를 줄여서 쓰고, 실제 네트워크는 쓰지 않는다."""

from collections.abc import Callable
from typing import Any

import httpx

from app.external.yes24.client import RateLimiter, Yes24Client

TEST_API_KEY = "test-yes24-key-value"


def item(isbn: str, **overrides: Any) -> dict[str, Any]:
    values = {
        "itemId": 15320,
        "title": "강아지똥",
        "subTitle": "",
        "author": "권정생 글/정승각 그림",
        "goodsType": "도서",
        "goodsSortNm": "국내도서-유아",
        "adultYn": "N",
        "publisher": "길벗어린이",
        "isbn13": isbn,
        "shopPrice": 14000,
        "salePrice": 12600,
        "publishDate": "19960401",
        "itemStatus": "판매중",
        "yesPoint": 140,
        "salePoint": 46881,
        "starScore": 9.5,
        "cover": "https://image.yes24.com/goods/15320/L",
        "link": "https://www.yes24.com/product/goods/15320",
        "contentDetail": {
            "bookIntroduction": "강아지똥이 민들레 꽃을 피워 내는 이야기",
            "bookSummary": None,
            "tableOfContents": None,
        },
        "series": [{"seriesId": 186, "seriesName": "민들레그림책"}],
    }
    return {**values, **overrides}


def ok(*items: dict[str, Any]) -> httpx.Response:
    data = {"items": list(items), "currentPage": 1, "pageSize": 1, "totalCount": len(items)}
    body = {"success": True, "message": "성공", "data": data, "errorCode": None}
    return httpx.Response(200, json=body)


def error(status: int, code: str | None = None) -> httpx.Response:
    body = {"success": False, "message": "오류", "data": None, "errorCode": code}
    return httpx.Response(status, json=body)


class FakeYes24:
    """ISBN별 응답을 정해 두고 호출을 기록한다. 정하지 않은 ISBN은 찾은 상품으로 답한다."""

    def __init__(self) -> None:
        self.responses: dict[str, httpx.Response | Exception] = {}
        self.requests: list[httpx.Request] = []

    @property
    def isbns(self) -> list[str]:
        return [r.url.params["query"] for r in self.requests]

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        isbn = request.url.params["query"]
        response = self.responses.get(isbn, ok(item(isbn)))
        if isinstance(response, Exception):
            raise response
        return response

    def client(self) -> Yes24Client:
        return make_client(self)


def make_client(handler: Callable[[httpx.Request], httpx.Response]) -> Yes24Client:
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://yes24.test/v1"
    )
    return Yes24Client(http, TEST_API_KEY, RateLimiter(0))
