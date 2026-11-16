"""YES24 호출 공통: 인증 헤더, 호출 속도 제한, 응답 해석, 오류 구분.

예외에는 중단 사유만 담는다. 요청 객체나 헤더를 넣지 않아 키가 메시지에 남지 않는다.
"""

from typing import Any

import httpx

from app.central.external.http import RateLimiter as _RateLimiter
from app.central.external.http import SourceStopped, StopReason
from app.central.external.yes24.definitions import (
    API_KEY_HEADER,
    MIN_CALL_INTERVAL_SECONDS,
    NOT_FOUND_ERROR_CODES,
    Endpoint,
)

SOURCE_NAME = "yes24"

__all__ = ["RateLimiter", "StopReason", "Yes24Client", "Yes24Stopped"]


class Yes24Stopped(SourceStopped):
    """실행을 멈춰야 하는 YES24 오류."""

    def __init__(self, reason: StopReason) -> None:
        super().__init__(SOURCE_NAME, reason)


class RateLimiter(_RateLimiter):
    """YES24 기본 간격을 쓰는 호출 간격 제한."""

    def __init__(self, min_interval: float = MIN_CALL_INTERVAL_SECONDS, **kwargs: Any) -> None:
        super().__init__(min_interval, **kwargs)


class Yes24Client:
    def __init__(
        self, http: httpx.AsyncClient, api_key: str, limiter: RateLimiter | None = None
    ) -> None:
        self._http = http
        self._api_key = api_key
        self._limiter = limiter or RateLimiter()

    async def get(self, endpoint: Endpoint, params: dict[str, str]) -> dict[str, Any] | None:
        """응답의 data를 돌려준다. 찾지 못한 결과는 None이고, 멈춰야 하면 Yes24Stopped다."""
        await self._limiter.wait()
        try:
            response = await self._http.get(
                endpoint.path, params=params, headers={API_KEY_HEADER: self._api_key}
            )
        except httpx.HTTPError:
            raise Yes24Stopped(StopReason.UPSTREAM_UNAVAILABLE) from None

        # 429는 문서에 오류 코드가 없어서 HTTP 상태로 판단한다.
        if response.status_code == httpx.codes.TOO_MANY_REQUESTS:
            raise Yes24Stopped(StopReason.RATE_LIMITED)
        if response.status_code == httpx.codes.UNAUTHORIZED:
            raise Yes24Stopped(StopReason.AUTH_FAILED)
        if response.status_code == httpx.codes.NOT_FOUND:
            return None
        body = _json(response)
        if response.status_code == httpx.codes.OK and body.get("success") is True:
            data = body.get("data")
            if isinstance(data, dict):
                return data
        if body.get("errorCode") in NOT_FOUND_ERROR_CODES:
            return None
        raise Yes24Stopped(StopReason.UPSTREAM_UNAVAILABLE)


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError:
        raise Yes24Stopped(StopReason.UPSTREAM_UNAVAILABLE) from None
    if not isinstance(body, dict):
        raise Yes24Stopped(StopReason.UPSTREAM_UNAVAILABLE)
    return body
