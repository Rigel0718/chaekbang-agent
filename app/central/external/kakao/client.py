"""카카오 책 검색 호출: 인증 헤더, 호출 간격, 응답 해석, 오류 구분.

예외에는 출처와 중단 사유만 담는다. 요청 객체나 헤더를 넣지 않아 키가 메시지에 남지 않는다.
"""

from typing import Any

import httpx

from app.central.external.http import RateLimiter, SourceStopped, StopReason
from app.central.external.kakao.definitions import (
    API_KEY_HEADER,
    API_KEY_PREFIX,
    BOOK_SEARCH,
    DOCUMENTS_KEY,
    MIN_CALL_INTERVAL_SECONDS,
    QUERY_PARAM,
    SOURCE_NAME,
    TARGET_ISBN,
    TARGET_PARAM,
    Endpoint,
)
from app.central.external.kakao.parsing import KakaoRecord, parse_document


def _stopped(reason: StopReason) -> SourceStopped:
    return SourceStopped(SOURCE_NAME, reason)


class KakaoClient:
    def __init__(
        self, http: httpx.AsyncClient, api_key: str, limiter: RateLimiter | None = None
    ) -> None:
        self._http = http
        self._api_key = api_key
        self._limiter = limiter or RateLimiter(MIN_CALL_INTERVAL_SECONDS)

    async def get(self, endpoint: Endpoint, params: dict[str, str]) -> dict[str, Any]:
        """응답 본문을 돌려준다. 멈춰야 하면 SourceStopped다."""
        await self._limiter.wait()
        try:
            response = await self._http.get(
                endpoint.path,
                params=params,
                headers={API_KEY_HEADER: API_KEY_PREFIX + self._api_key},
            )
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
        if not isinstance(body, dict):
            raise _stopped(StopReason.UPSTREAM_UNAVAILABLE)
        return body


async def raw_documents_by_isbn(client: KakaoClient, isbn: str) -> list[dict[str, Any]]:
    """ISBN으로 찾은 문서 원본. 찾지 못하면 빈 목록이다. 원본을 파일에 남길 때 쓴다."""
    body = await client.get(BOOK_SEARCH, {QUERY_PARAM: isbn, TARGET_PARAM: TARGET_ISBN})
    documents = body.get(DOCUMENTS_KEY)
    if not isinstance(documents, list):
        raise _stopped(StopReason.UPSTREAM_UNAVAILABLE)
    return [document for document in documents if isinstance(document, dict)]


async def get_documents_by_isbn(client: KakaoClient, isbn: str) -> list[KakaoRecord]:
    """ISBN으로 책을 검색한다. 찾지 못하면 빈 목록이다. 다른 ISBN의 문서가 섞여 올 수 있다."""
    return [parse_document(document) for document in await raw_documents_by_isbn(client, isbn)]
