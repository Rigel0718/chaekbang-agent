"""[catalog/bibliographic-sources] 정보나루 대출 신호 응답 해석: 이용 분석과 인기대출도서."""

import logging
from datetime import date

import httpx
import pytest

from app.central.external.data4library.client import popular_loans, usage_analysis
from app.central.external.data4library.definitions import AGE_ALL, AGE_CHILDREN
from app.central.external.data4library.parsing import list_isbn
from app.central.external.http import SourceStopped, StopReason
from tests.helpers import VALID_ISBN, make_isbn
from tests.source_helpers import (
    TEST_D4L_KEY,
    d4l_error,
    d4l_list_book,
    d4l_not_found,
    d4l_popular,
    d4l_popular_doc,
    d4l_usage,
    make_d4l_client,
)


def _client(response):  # noqa: ANN001, ANN202
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if isinstance(response, Exception):
            raise response
        return response

    return make_d4l_client(handler), requests


def _hyphenated(isbn: str) -> str:
    return f"{isbn[:3]}-{isbn[3:5]}-{isbn[5:9]}-{isbn[9:12]}-{isbn[12]}"


async def test_co_loan_order() -> None:
    """[catalog/bibliographic-sources] 정보나루 대출 신호 응답 해석 / 함께 대출 순서"""
    a, b = make_isbn(1), make_isbn(2)
    books = [d4l_list_book(_hyphenated(a)), d4l_list_book(b), d4l_list_book(b)]
    client, requests = _client(d4l_usage(books))
    result = await usage_analysis(client, VALID_ISBN)
    assert result is not None
    assert result.co_loans == (a, b)
    assert result.loan_count == 321
    (request,) = requests
    assert request.url.path.endswith("/usageAnalysisList")
    assert request.url.params["isbn13"] == VALID_ISBN


@pytest.mark.parametrize("bad", ["", "  ", "12345", "9780306406158", None])
async def test_invalid_isbn_is_dropped(bad) -> None:
    """[catalog/bibliographic-sources] 정보나루 대출 신호 응답 해석 / 잘못된 ISBN"""
    a, b = make_isbn(3), make_isbn(4)
    books = [d4l_list_book(a), d4l_list_book(bad), d4l_list_book(b)]
    client, _ = _client(d4l_usage(books))
    result = await usage_analysis(client, VALID_ISBN)
    assert result is not None and result.co_loans == (a, b)


def test_isbn10_is_converted() -> None:
    """[catalog/bibliographic-sources] 정보나루 대출 신호 응답 해석 (10자리 ISBN은 13자리로)"""
    assert list_isbn("0-306-40615-2") == "9780306406157"


async def test_three_rankings() -> None:
    """[catalog/bibliographic-sources] 정보나루 대출 신호 응답 해석 (마니아·다독자 추천)"""
    client, _ = _client(
        d4l_usage(
            [d4l_list_book(make_isbn(5))],
            mania=[d4l_list_book(make_isbn(6))],
            reader=[d4l_list_book(make_isbn(7)), d4l_list_book(make_isbn(8))],
        )
    )
    result = await usage_analysis(client, VALID_ISBN)
    assert result is not None
    assert (result.co_loans, result.mania, result.reader) == (
        (make_isbn(5),),
        (make_isbn(6),),
        (make_isbn(7), make_isbn(8)),
    )


@pytest.mark.parametrize(
    "response",
    [
        d4l_usage([]),
        httpx.Response(200, json={"response": {"book": {"loanCnt": "3"}}}),
        httpx.Response(200, json={"response": {"book": {}, "coLoanBooks": None}}),
    ],
)
async def test_empty_co_loans(response) -> None:
    """[catalog/bibliographic-sources] 정보나루 대출 신호 응답 해석 / 함께 대출이 비어 있음"""
    client, _ = _client(response)
    result = await usage_analysis(client, VALID_ISBN)
    assert result is not None
    assert result.co_loans == ()


async def test_single_object_list() -> None:
    """[catalog/bibliographic-sources] 정보나루 대출 신호 응답 해석 (목록이 한 건 객체로 오는 꼴)"""
    body = {"response": {"book": {}, "coLoanBooks": {"book": d4l_list_book(make_isbn(9))}}}
    client, _ = _client(httpx.Response(200, json=body))
    result = await usage_analysis(client, VALID_ISBN)
    assert result is not None and result.co_loans == (make_isbn(9),)


async def test_not_found() -> None:
    """[catalog/bibliographic-sources] 정보나루 대출 신호 응답 해석 / 찾지 못한 도서"""
    client, _ = _client(d4l_not_found())
    assert await usage_analysis(client, VALID_ISBN) is None


async def test_popular_reads_only_ranking() -> None:
    """[catalog/bibliographic-sources] 정보나루 대출 신호 응답 해석 / 읽지 않는 값"""
    a, b = make_isbn(10), make_isbn(11)
    client, requests = _client(d4l_popular(d4l_popular_doc(a, 1, 900), d4l_popular_doc(b, 2, 800)))
    result = await popular_loans(client, AGE_CHILDREN, date(2025, 11, 17), date(2026, 11, 16), 1000)
    assert result.isbns == (a, b)
    assert result.loan_counts == (900, 800)
    assert set(vars(result)) == {"isbns", "loan_counts"}
    assert "image.example" not in repr(result)
    (request,) = requests
    assert request.url.path.endswith("/loanItemSrch")
    params = request.url.params
    assert (params["age"], params["startDt"], params["endDt"], params["pageSize"]) == (
        "0;6;8",
        "2025-11-17",
        "2026-11-16",
        "1000",
    )


async def test_popular_without_age() -> None:
    """[catalog/bibliographic-sources] 정보나루 대출 신호 응답 해석 (전체 연령은 조건 없음)"""
    client, requests = _client(d4l_popular())
    result = await popular_loans(client, AGE_ALL, date(2026, 8, 18), date(2026, 11, 16), 1000)
    assert result.isbns == ()
    assert "age" not in requests[0].url.params


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (d4l_error("일일 호출 건수를 초과했습니다."), StopReason.RATE_LIMITED),
        (d4l_error("인증정보가 일치하지 않습니다."), StopReason.AUTH_FAILED),
        (httpx.Response(503), StopReason.UPSTREAM_UNAVAILABLE),
        (httpx.ReadTimeout("시간 초과"), StopReason.UPSTREAM_UNAVAILABLE),
    ],
)
async def test_stop_reasons(response, reason: StopReason, caplog) -> None:  # noqa: ANN001
    """[catalog/bibliographic-sources] 정보나루 대출 신호 응답 해석 / 키 보호 (중단 사유)"""
    caplog.set_level(logging.INFO)
    for call in (
        lambda c: usage_analysis(c, VALID_ISBN),
        lambda c: popular_loans(c, AGE_ALL, date(2026, 1, 1), date(2026, 2, 1), 10),
    ):
        client, _ = _client(response)
        with pytest.raises(SourceStopped) as caught:
            await call(client)
        assert caught.value.reason == reason
        assert TEST_D4L_KEY not in str(caught.value) + repr(caught.value)
    assert TEST_D4L_KEY not in caplog.text


async def test_key_in_query_only() -> None:
    """[catalog/bibliographic-sources] 정보나루 대출 신호 응답 해석 / 키 보호 (쿼리로만)"""
    client, requests = _client(d4l_popular())
    await popular_loans(client, AGE_ALL, date(2026, 1, 1), date(2026, 2, 1), 10)
    (request,) = requests
    assert request.url.params["authKey"] == TEST_D4L_KEY
    assert TEST_D4L_KEY not in " ".join(f"{k}={v}" for k, v in request.headers.items())


async def test_real_usage_shape() -> None:
    """[catalog/bibliographic-sources] 정보나루 대출 신호 응답 해석 (확인 호출로 본 꼴, 2026-11-17)

    기준 책 대출 수가 정수로 오고, 함께 대출 원소에는 대출 수가 없다.
    """
    book = d4l_list_book(make_isbn(12))
    del book["loanCnt"], book["bookImageURL"]
    client, _ = _client(d4l_usage([book], loan_count=46344))
    result = await usage_analysis(client, VALID_ISBN)
    assert result is not None
    assert (result.co_loans, result.loan_count) == ((make_isbn(12),), 46344)
