"""정보나루 호출: 키 전달, 호출 간격, 응답 해석, 오류 구분.

이 API는 키를 쿼리 파라미터로만 받는다. 키를 붙이는 곳은 이 모듈 하나다. `httpx` 예외는 URL을
담고 있어 사슬 없이 `SourceStopped`로 바꾼다(키가 오류 메시지에 남지 않게).
"""

from datetime import date
from typing import Any

import httpx

from app.central.external.data4library.definitions import (
    AGE_PARAM,
    API_KEY_PARAM,
    AUTH_ERROR_WORDS,
    BOOK_DETAIL,
    BOOK_KEY,
    DETAIL_KEY,
    END_PARAM,
    ERROR_CODE_KEY,
    ERROR_KEY,
    FORMAT_JSON,
    FORMAT_PARAM,
    ISBN_PARAM,
    LIMIT_ERROR_WORDS,
    MIN_CALL_INTERVAL_SECONDS,
    NOT_FOUND_ERROR_CODES,
    PAGE_SIZE_PARAM,
    POPULAR_LOANS,
    RESPONSE_KEY,
    SOURCE_NAME,
    START_PARAM,
    USAGE_ANALYSIS,
    AgeGroup,
    Endpoint,
)
from app.central.external.data4library.parsing import (
    Data4LibraryRecord,
    PopularLoans,
    UsageAnalysis,
    parse_book,
    parse_popular,
    parse_usage,
)
from app.central.external.http import RateLimiter, SourceStopped, StopReason


def _stopped(reason: StopReason) -> SourceStopped:
    return SourceStopped(SOURCE_NAME, reason)


class Data4LibraryClient:
    def __init__(
        self, http: httpx.AsyncClient, api_key: str, limiter: RateLimiter | None = None
    ) -> None:
        self._http = http
        self._api_key = api_key
        self._limiter = limiter or RateLimiter(MIN_CALL_INTERVAL_SECONDS)

    async def get(self, endpoint: Endpoint, params: dict[str, str]) -> dict[str, Any]:
        """응답의 `response`를 돌려준다. 멈춰야 하면 SourceStopped다."""
        await self._limiter.wait()
        query = {**params, FORMAT_PARAM: FORMAT_JSON, API_KEY_PARAM: self._api_key}
        try:
            response = await self._http.get(endpoint.path, params=query)
        except httpx.HTTPError:
            raise _stopped(StopReason.UPSTREAM_UNAVAILABLE) from None

        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            raise _stopped(StopReason.RATE_LIMITED)
        if response.status_code in (httpx.codes.UNAUTHORIZED, httpx.codes.FORBIDDEN):
            raise _stopped(StopReason.AUTH_FAILED)
        if response.status_code != httpx.codes.OK:
            raise _stopped(StopReason.UPSTREAM_UNAVAILABLE)
        try:
            body = response.json()
        except ValueError:
            raise _stopped(StopReason.UPSTREAM_UNAVAILABLE) from None
        data = body.get(RESPONSE_KEY) if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise _stopped(StopReason.UPSTREAM_UNAVAILABLE)
        error = data.get(ERROR_KEY)
        if error:
            if data.get(ERROR_CODE_KEY) in NOT_FOUND_ERROR_CODES:
                return {}  # 찾지 못함: 도서가 없는 응답과 같다
            raise _stopped(_error_reason(str(error)))
        return data


def _error_reason(message: str) -> StopReason:
    """오류 문구로 사유를 가른다. 이 API는 오류도 200으로 돌려준다."""
    if any(word in message for word in LIMIT_ERROR_WORDS):
        return StopReason.RATE_LIMITED
    if any(word in message for word in AUTH_ERROR_WORDS):
        return StopReason.AUTH_FAILED
    return StopReason.UPSTREAM_UNAVAILABLE


def _books(data: dict[str, Any]) -> list[dict[str, Any]]:
    """`detail` 아래의 도서들. 목록으로도, 한 건으로도 올 수 있다."""
    detail = data.get(DETAIL_KEY)
    entries = detail if isinstance(detail, list) else [detail]
    books = []
    for entry in entries:
        book = entry.get(BOOK_KEY) if isinstance(entry, dict) else None
        if isinstance(book, dict):
            books.append(book)
    return books


async def raw_books_by_isbn(client: Data4LibraryClient, isbn: str) -> list[dict[str, Any]]:
    """ISBN의 도서 상세 원본. 찾지 못하면 빈 목록이다. 원본을 파일에 남길 때 쓴다."""
    return _books(await client.get(BOOK_DETAIL, {ISBN_PARAM: isbn}))


async def get_books_by_isbn(client: Data4LibraryClient, isbn: str) -> list[Data4LibraryRecord]:
    """ISBN으로 도서 상세를 조회한다. 찾지 못하면 빈 목록이다."""
    return [parse_book(book) for book in await raw_books_by_isbn(client, isbn)]


async def usage_analysis(client: Data4LibraryClient, isbn: str) -> UsageAnalysis | None:
    """도서별 이용 분석의 ISBN 순위. 찾지 못한 도서면 None이다."""
    data = await client.get(USAGE_ANALYSIS, {ISBN_PARAM: isbn})
    return parse_usage(data) if data else None


async def popular_loans(
    client: Data4LibraryClient, age: AgeGroup, start: date, end: date, page_size: int
) -> PopularLoans:
    """전국 인기대출도서의 순위. 결과가 없으면 빈 순위다."""
    params = {
        START_PARAM: start.isoformat(),
        END_PARAM: end.isoformat(),
        PAGE_SIZE_PARAM: str(page_size),
    }
    if age.age is not None:
        params[AGE_PARAM] = age.age
    return parse_popular(await client.get(POPULAR_LOANS, params))
