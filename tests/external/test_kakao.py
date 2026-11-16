"""[catalog/bibliographic-sources] 카카오 책 검색 호출과 응답 해석: 값 읽기, 오류 구분, 키 전달."""

from datetime import date

import httpx
import pytest

from app.central.external.http import RateLimiter, SourceStopped, StopReason
from app.central.external.kakao.client import get_documents_by_isbn
from app.central.external.kakao.definitions import MIN_CALL_INTERVAL_SECONDS
from app.central.external.kakao.parsing import (
    isbn13_of,
    join_authors,
    parse_document,
    strip_volatile,
)
from app.core.contributors import ContributorRole, parse_author_text
from tests.helpers import VALID_ISBN, VALID_ISBN_2
from tests.source_helpers import TEST_KAKAO_KEY, FakeKakao, kakao_document, kakao_ok


async def _call(response) -> list:
    fake = FakeKakao()
    fake.responses[VALID_ISBN] = response
    return await get_documents_by_isbn(fake.client(), VALID_ISBN)


async def test_found() -> None:
    """[catalog/bibliographic-sources] 카카오 응답 해석 (문서 한 건)"""
    (record,) = await _call(kakao_ok(kakao_document(VALID_ISBN)))
    assert record.isbn13 == VALID_ISBN
    assert (record.title, record.author, record.publisher) == ("강아지똥", "권정생", "길벗어린이")
    assert record.list_price == 14000
    assert record.cover_url == "https://search1.kakaocdn.net/thumb/cover"
    assert record.url.startswith("https://search.daum.net/")


def test_isbn10_and_isbn13() -> None:
    """[catalog/bibliographic-sources] 카카오 응답 해석 / ISBN10과 ISBN13"""
    assert isbn13_of({"isbn": "8996991341 9788996991342"}) == "9788996991342"
    assert isbn13_of({"isbn": "9788996991342"}) == "9788996991342"
    assert isbn13_of({"isbn": "8996991341"}) is None
    assert isbn13_of({"isbn": ""}) is None
    assert isbn13_of({}) is None


async def test_other_isbn_documents_are_returned_as_they_are() -> None:
    """[catalog/bibliographic-sources] 카카오 응답 해석 / 다른 ISBN 문서만 있음

    같은 ISBN인지 가르는 것은 합치는 쪽이다. 여기서는 문서의 ISBN13을 그대로 돌려준다.
    """
    (record,) = await _call(kakao_ok(kakao_document(VALID_ISBN_2)))
    assert record.isbn13 == VALID_ISBN_2


async def test_empty_documents() -> None:
    """[catalog/book-enrichment] 찾지 못한 도서 / 결과가 빈 성공 응답"""
    assert await _call(kakao_ok()) == []


def test_iso_datetime() -> None:
    """[catalog/bibliographic-sources] 카카오 응답 해석 / ISO 출간일

    [catalog/book-enrichment] 응답 값 정규화 / ISO 날짜·시각
    """
    document = kakao_document(VALID_ISBN, datetime="2014-11-17T00:00:00.000+09:00")
    assert parse_document(document).published_date == date(2014, 11, 17)
    assert parse_document(kakao_document(VALID_ISBN, datetime="")).published_date is None


@pytest.mark.parametrize("price", [0, -1, None, "", "무료"])
def test_price_zero_is_empty(price) -> None:
    """[catalog/bibliographic-sources] 카카오 응답 해석 / 정가 0"""
    assert parse_document(kakao_document(VALID_ISBN, price=price)).list_price is None


def test_volatile_values_are_not_read() -> None:
    """[catalog/book-enrichment] 저장하지 않는 값 / 변동 정보 미저장"""
    document = kakao_document(VALID_ISBN, sale_price=12345, status="품절임박")
    text = repr(parse_document(document))
    assert "12345" not in text
    assert "품절임박" not in text
    assert set(strip_volatile(document)) == set(document) - {"sale_price", "status"}


def test_two_authors_and_translator() -> None:
    """[catalog/book-contributors] 카카오 저자 배열 해석 / 저자 둘과 역자 하나"""
    text = join_authors(["칼 멜링", "브라이트 스타"], ["김맑아"])
    assert text == "칼 멜링, 브라이트 스타 ;옮긴이: 김맑아"
    assert [(p.name, p.role) for p in parse_author_text(text)] == [
        ("칼 멜링", ContributorRole.AUTHOR),
        ("브라이트 스타", ContributorRole.AUTHOR),
        ("김맑아", ContributorRole.TRANSLATOR),
    ]


def test_no_translator() -> None:
    """[catalog/book-contributors] 카카오 저자 배열 해석 / 역자 없음"""
    assert join_authors(["한강"], []) == "한강"
    assert [(p.name, p.role) for p in parse_author_text("한강")] == [
        ("한강", ContributorRole.AUTHOR)
    ]


def test_empty_names_are_dropped() -> None:
    """[catalog/book-contributors] 카카오 저자 배열 해석 / 빈 이름"""
    document = kakao_document(VALID_ISBN, authors=["백희나", "", "  "], translators=[""])
    assert parse_document(document).author == "백희나"
    assert parse_document(kakao_document(VALID_ISBN, authors=[])).author is None


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(429), StopReason.RATE_LIMITED),
        (httpx.Response(401), StopReason.AUTH_FAILED),
        (httpx.Response(403), StopReason.AUTH_FAILED),
        (httpx.Response(503), StopReason.UPSTREAM_UNAVAILABLE),
        (httpx.Response(400), StopReason.UPSTREAM_UNAVAILABLE),
        (httpx.Response(200, text="<html>"), StopReason.UPSTREAM_UNAVAILABLE),
        (httpx.Response(200, json=[]), StopReason.UPSTREAM_UNAVAILABLE),
        (httpx.Response(200, json={"meta": {}}), StopReason.UPSTREAM_UNAVAILABLE),
        (httpx.ReadTimeout("시간 초과"), StopReason.UPSTREAM_UNAVAILABLE),
    ],
)
async def test_stop_results(response, reason: StopReason) -> None:
    """[catalog/book-enrichment] 외부 장애 시 중단 (카카오 오류 구분)"""
    with pytest.raises(SourceStopped) as caught:
        await _call(response)
    assert caught.value.source == "kakao"
    assert caught.value.reason == reason
    assert TEST_KAKAO_KEY not in str(caught.value)


async def test_interval_between_calls() -> None:
    """[catalog/book-enrichment] 호출 속도 제한 / 연속 호출 간격 (카카오 0.2초)"""
    assert MIN_CALL_INTERVAL_SECONDS == 0.2
    now = 100.0
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        nonlocal now
        waits.append(seconds)
        now += seconds

    fake = FakeKakao()
    client = fake.client(RateLimiter(MIN_CALL_INTERVAL_SECONDS, clock=lambda: now, sleep=sleep))
    for isbn in (VALID_ISBN, VALID_ISBN_2, VALID_ISBN):
        await get_documents_by_isbn(client, isbn)
    assert waits == [0.2, 0.2]


async def test_key_goes_in_header_only() -> None:
    """[catalog/book-enrichment] API 키 보호 / 키 헤더 전송"""
    fake = FakeKakao()
    await get_documents_by_isbn(fake.client(), VALID_ISBN)
    (request,) = fake.requests
    assert request.headers["Authorization"] == f"KakaoAK {TEST_KAKAO_KEY}"
    assert TEST_KAKAO_KEY not in str(request.url)
    assert request.url.params["target"] == "isbn"


def test_real_document_shape() -> None:
    """[catalog/bibliographic-sources] 카카오 응답 해석 (확인 호출로 본 꼴, 2026-11-16)"""
    document = kakao_document(
        "9788955823509",
        title="엄마가 유령이 되었어!",
        authors=["노부미"],
        translators=["이기웅"],
        datetime="2016-05-15T00:00:00.000+09:00",
        price=12000,
    ) | {"isbn": "8955823509 9788955823509"}
    record = parse_document(document)
    assert record.isbn13 == "9788955823509"
    assert record.author == "노부미 ;옮긴이: 이기웅"
    assert record.published_date == date(2016, 5, 15)
