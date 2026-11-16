"""정보나루·카카오 응답 픽스처와 가짜 서버. 실제 응답 구조를 줄여서 쓰고 네트워크는 쓰지 않는다."""

from collections.abc import Callable
from typing import Any

import httpx

from app.central.external.data4library.client import Data4LibraryClient
from app.central.external.http import RateLimiter
from app.central.external.kakao.client import KakaoClient

TEST_D4L_KEY = "test-data4library-key-value"
TEST_KAKAO_KEY = "test-kakao-key-value"


def d4l_book(isbn: str, **overrides: Any) -> dict[str, Any]:
    values = {
        "no": 1,
        "bookname": "강아지똥 :권정생 그림책",
        "authors": "지은이: 권정생 ;그림: 정승각",
        "publisher": "길벗어린이",
        "publication_date": "1996",
        "publication_year": "1996",
        "isbn": "",
        "isbn13": isbn,
        "addition_symbol": "77810",
        "vol": "",
        "class_no": "813.8",
        "class_nm": "문학 > 한국문학 > 동화",
        "description": "강아지똥이 민들레 꽃을 피워 내는 이야기",
        "bookImageURL": "https://image.example/d4l/cover.jpg",
    }
    return {**values, **overrides}


def d4l_ok(*books: dict[str, Any]) -> httpx.Response:
    body = {"response": {"request": {}, "detail": [{"book": book} for book in books]}}
    return httpx.Response(200, json=body)


def d4l_error(message: str, code: str | None = None) -> httpx.Response:
    body = {"error": message} | ({"errCode": code} if code else {})
    return httpx.Response(200, json={"response": body})


def d4l_not_found() -> httpx.Response:
    """정보나루가 찾지 못한 도서에 돌려주는 실제 꼴(확인 2026-11-16)."""
    return d4l_error("ISBN에 해당하는 도서가 없습니다.", "isbnMpngErr")


def kakao_document(isbn: str, **overrides: Any) -> dict[str, Any]:
    values = {
        "title": "강아지똥",
        "contents": "강아지똥이 민들레 꽃을 피워 내는",
        "url": "https://search.daum.net/search?w=bookpage&bookId=1",
        "isbn": f"8900000000 {isbn}",
        "datetime": "1996-04-01T00:00:00.000+09:00",
        "authors": ["권정생"],
        "publisher": "길벗어린이",
        "translators": [],
        "price": 14000,
        "sale_price": 12600,
        "thumbnail": "https://search1.kakaocdn.net/thumb/cover",
        "status": "정상판매",
    }
    return {**values, **overrides}


def kakao_ok(*documents: dict[str, Any]) -> httpx.Response:
    meta = {"is_end": True, "pageable_count": len(documents), "total_count": len(documents)}
    return httpx.Response(200, json={"meta": meta, "documents": list(documents)})


class _FakeServer:
    """ISBN별 응답을 정해 두고 호출을 기록한다. 정하지 않은 ISBN은 찾은 책으로 답한다."""

    isbn_param = ""

    def __init__(self) -> None:
        self.responses: dict[str, httpx.Response | Exception] = {}
        self.requests: list[httpx.Request] = []

    @property
    def isbns(self) -> list[str]:
        return [r.url.params[self.isbn_param] for r in self.requests]

    def default(self, isbn: str) -> httpx.Response:
        raise NotImplementedError

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        isbn = request.url.params[self.isbn_param]
        response = self.responses.get(isbn)
        if response is None:
            return self.default(isbn)
        if isinstance(response, Exception):
            raise response
        return response


class FakeData4Library(_FakeServer):
    isbn_param = "isbn13"

    def default(self, isbn: str) -> httpx.Response:
        return d4l_ok(d4l_book(isbn))

    def client(self, limiter: RateLimiter | None = None) -> Data4LibraryClient:
        return make_d4l_client(self, limiter)


class FakeKakao(_FakeServer):
    isbn_param = "query"

    def default(self, isbn: str) -> httpx.Response:
        return kakao_ok(kakao_document(isbn))

    def client(self, limiter: RateLimiter | None = None) -> KakaoClient:
        return make_kakao_client(self, limiter)


Handler = Callable[[httpx.Request], httpx.Response]


def make_d4l_client(handler: Handler, limiter: RateLimiter | None = None) -> Data4LibraryClient:
    http = httpx.AsyncClient(
        transport=httpx.MockTransport(handler), base_url="https://data4library.test/api"
    )
    return Data4LibraryClient(http, TEST_D4L_KEY, limiter or RateLimiter(0))


def make_kakao_client(handler: Handler, limiter: RateLimiter | None = None) -> KakaoClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://kakao.test")
    return KakaoClient(http, TEST_KAKAO_KEY, limiter or RateLimiter(0))


class FakeSources:
    """가짜 정보나루, 카카오, YES24 묶음. 채움 실행과 같은 조회(`lookup_sources`)를 만든다."""

    def __init__(self) -> None:
        from tests.yes24_helpers import FakeYes24

        self.data4library = FakeData4Library()
        self.kakao = FakeKakao()
        self.yes24 = FakeYes24()

    def lookup(self):  # noqa: ANN201 - Lookup
        from app.central.enrichment import lookup_sources

        return lookup_sources(self.data4library.client(), self.kakao.client(), self.yes24.client())

    @property
    def calls(self) -> int:
        return len(self.data4library.requests) + len(self.kakao.requests) + len(self.yes24.requests)


async def enrich_sources(session, sources: FakeSources | None = None, **options: Any):  # noqa: ANN001, ANN201
    """운영자 실행과 같이 접점을 이어서 채움을 돌린다(세 출처 조회로)."""
    from app.central.enrichment import run_enrichment
    from app.library.enrichment_targets import LibraryEnrichmentTargets

    sources = sources or FakeSources()
    return await run_enrichment(
        session, sources.lookup(), LibraryEnrichmentTargets(session), **options
    )
