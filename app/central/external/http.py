"""외부 서지 출처 호출의 공통 조각: 호출 간격, 중단 사유, 중단 예외.

예외에는 출처 이름과 중단 사유만 담는다. 요청 객체, URL, 헤더를 넣지 않아 키가 메시지에 남지 않는다.
"""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from enum import StrEnum

# httpx는 INFO 수준에서 요청 URL을 로그에 쓴다. 키를 쿼리로만 받는 출처(정보나루)가 있어
# 앱의 로그 수준과 상관없이 요청 줄이 나오지 않게 한다.
for _name in ("httpx", "httpcore"):
    logging.getLogger(_name).setLevel(logging.WARNING)


class StopReason(StrEnum):
    RATE_LIMITED = "rate_limited"
    AUTH_FAILED = "auth_failed"
    UPSTREAM_UNAVAILABLE = "upstream_unavailable"


class SourceStopped(Exception):
    """실행을 멈춰야 하는 외부 오류. 어느 출처의 무슨 사유인지만 담는다."""

    def __init__(self, source: str, reason: StopReason) -> None:
        super().__init__(f"{source}: {reason.value}")
        self.source = source
        self.reason = reason


class RateLimiter:
    """호출 사이를 min_interval초 이상 벌린다."""

    def __init__(
        self,
        min_interval: float,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last_call: float | None = None

    async def wait(self) -> None:
        if self._last_call is not None:
            remaining = self._min_interval - (self._clock() - self._last_call)
            if remaining > 0:
                await self._sleep(remaining)
        self._last_call = self._clock()
