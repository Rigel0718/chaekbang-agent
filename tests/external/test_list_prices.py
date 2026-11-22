"""[library/purchase-requests] 정가 조회: YES24 상품 상세의 정가만 읽고, 장애는 사유로 알린다."""

import httpx
import pytest

from app.central.external.yes24.client import StopReason
from app.central.list_prices import PriceLookupUnavailable, UnconfiguredListPrices, Yes24ListPrices
from tests.helpers import VALID_ISBN, VALID_ISBN_2
from tests.yes24_helpers import FakeYes24, error, item, ok


def _prices(fake: FakeYes24) -> Yes24ListPrices:
    return Yes24ListPrices(fake.client())


async def test_list_price_only() -> None:
    """[library/purchase-requests] 정가 조회 / 정가만 씀: 판매가 13,500원은 읽지 않는다"""
    fake = FakeYes24()
    fake.responses[VALID_ISBN] = ok(item(VALID_ISBN, shopPrice=15000, salePrice=13500))
    assert await _prices(fake).lookup([VALID_ISBN]) == {VALID_ISBN: 15000}


async def test_other_isbn_item_is_no_price() -> None:
    """[library/purchase-requests] 정가 조회 / 다른 ISBN 상품: 같은 ISBN13 상품만 쓴다"""
    fake = FakeYes24()
    fake.responses[VALID_ISBN] = ok(item(VALID_ISBN_2, shopPrice=15000))
    assert await _prices(fake).lookup([VALID_ISBN]) == {VALID_ISBN: None}


@pytest.mark.parametrize(
    "response",
    [
        ok(),
        error(404, "GOODS_002"),
        ok(item(VALID_ISBN, shopPrice=0)),
        ok(item(VALID_ISBN, shopPrice=None)),
    ],
)
async def test_missing_or_zero_price_is_none(response: httpx.Response) -> None:
    """[library/purchase-requests] 정가 조회 / 정가가 없거나 0이면 가격 없음"""
    fake = FakeYes24()
    fake.responses[VALID_ISBN] = response
    assert await _prices(fake).lookup([VALID_ISBN]) == {VALID_ISBN: None}


async def test_same_isbn_is_looked_up_once() -> None:
    """[library/purchase-requests] 정가 조회 / 같은 ISBN을 겹쳐 넣어도 한 번만 부른다"""
    fake = FakeYes24()
    result = await _prices(fake).lookup([VALID_ISBN, VALID_ISBN_2, VALID_ISBN])
    assert list(result) == [VALID_ISBN, VALID_ISBN_2]
    assert fake.isbns == [VALID_ISBN, VALID_ISBN_2]


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(429), StopReason.RATE_LIMITED),
        (error(401, "AUTH_002"), StopReason.AUTH_FAILED),
        (error(503, "UPSTREAM_UNAVAILABLE"), StopReason.UPSTREAM_UNAVAILABLE),
        (httpx.ReadTimeout("시간 초과"), StopReason.UPSTREAM_UNAVAILABLE),
    ],
)
async def test_outage_is_unavailable(response, reason: StopReason) -> None:
    """[library/purchase-requests] 승인 때 조회 실패 / 장애는 부분 결과 없이 사유로 알린다"""
    fake = FakeYes24()
    fake.responses[VALID_ISBN_2] = response
    with pytest.raises(PriceLookupUnavailable) as caught:
        await _prices(fake).lookup([VALID_ISBN, VALID_ISBN_2])
    assert caught.value.reason == reason


async def test_unconfigured_is_unavailable() -> None:
    """[library/purchase-requests] 승인 때 조회 실패 / 키가 없으면 쓸 수 없다"""
    with pytest.raises(PriceLookupUnavailable):
        await UnconfiguredListPrices().lookup([VALID_ISBN])
