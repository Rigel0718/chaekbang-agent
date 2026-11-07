"""[catalog/book-enrichment] YES24 호출: 오류 구분, 호출 속도, 키 전송."""

import httpx
import pytest

from app.external.yes24.client import RateLimiter, StopReason, Yes24Stopped
from app.external.yes24.definitions import MIN_CALL_INTERVAL_SECONDS
from app.external.yes24.goods import get_items_by_isbn
from tests.helpers import VALID_ISBN, VALID_ISBN_2
from tests.yes24_helpers import TEST_API_KEY, FakeYes24, error, item, ok


async def _call(response) -> list:
    fake = FakeYes24()
    fake.responses[VALID_ISBN] = response
    return await get_items_by_isbn(fake.client(), VALID_ISBN)


async def test_found() -> None:
    """[catalog/book-enrichment] 공식 서지 만들기 (상품 응답 해석)"""
    items = await _call(ok(item(VALID_ISBN)))
    assert [i.isbn13 for i in items] == [VALID_ISBN]


@pytest.mark.parametrize(
    "response",
    [
        error(404, "GOODS_002"),
        error(404, "SEARCH_002"),
        error(404, "AUTHOR_404"),
        error(400, "PARAM_004"),
        ok(),
    ],
)
async def test_not_found_results(response) -> None:
    """[catalog/book-enrichment] 찾지 못한 도서 / 상품 없음 (design 오류 구분 표)"""
    assert await _call(response) == []


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(429), StopReason.RATE_LIMITED),
        (error(401, "AUTH_002"), StopReason.AUTH_FAILED),
        (error(503, "UPSTREAM_UNAVAILABLE"), StopReason.UPSTREAM_UNAVAILABLE),
        (error(500), StopReason.UPSTREAM_UNAVAILABLE),
        (error(400, "PARAM_999"), StopReason.UPSTREAM_UNAVAILABLE),
        (httpx.Response(200, text="<html>"), StopReason.UPSTREAM_UNAVAILABLE),
        (httpx.Response(200, json=[]), StopReason.UPSTREAM_UNAVAILABLE),
        (
            httpx.Response(200, json={"success": True, "data": None}),
            StopReason.UPSTREAM_UNAVAILABLE,
        ),
        (httpx.Response(200, json={"success": True, "data": {}}), StopReason.UPSTREAM_UNAVAILABLE),
        (httpx.ReadTimeout("시간 초과"), StopReason.UPSTREAM_UNAVAILABLE),
        (httpx.ConnectError("연결 실패"), StopReason.UPSTREAM_UNAVAILABLE),
    ],
)
async def test_stop_results(response, reason: StopReason) -> None:
    """[catalog/book-enrichment] 외부 장애 시 중단 (design 오류 구분 표)"""
    with pytest.raises(Yes24Stopped) as caught:
        await _call(response)
    assert caught.value.reason == reason


async def test_interval_between_calls() -> None:
    """[catalog/book-enrichment] 호출 속도 제한 / 연속 호출 간격"""
    now = 100.0
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        nonlocal now
        waits.append(seconds)
        now += seconds

    limiter = RateLimiter(0.2, clock=lambda: now, sleep=sleep)
    await limiter.wait()
    await limiter.wait()
    now += 0.05
    await limiter.wait()
    now += 0.5
    await limiter.wait()
    assert waits == pytest.approx([0.2, 0.15])


def test_default_interval_is_within_limit() -> None:
    """[catalog/book-enrichment] 호출 속도 제한 / 연속 호출 간격 (기본값은 초당 5회)"""
    assert MIN_CALL_INTERVAL_SECONDS == 0.2


async def test_key_is_sent_in_header_only() -> None:
    """[catalog/book-enrichment] API 키 보호 / 키 헤더 전송"""
    fake = FakeYes24()
    await get_items_by_isbn(fake.client(), VALID_ISBN_2)
    request = fake.requests[0]
    assert request.headers["X-Api-Key"] == TEST_API_KEY
    assert TEST_API_KEY not in str(request.url)
    assert request.url.params["searchType"] == "ISBN13"
    assert request.url.params["detail"] == "Y"
    assert request.url.path == "/v1/goods/itemDetail"


async def test_stop_error_has_no_key() -> None:
    """[catalog/book-enrichment] API 키 보호 / 오류에 키 없음 (예외 메시지)"""
    with pytest.raises(Yes24Stopped) as caught:
        await _call(httpx.ConnectError(f"연결 실패 {TEST_API_KEY}"))
    assert TEST_API_KEY not in str(caught.value)
    assert caught.value.__cause__ is None
