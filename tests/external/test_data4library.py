"""[catalog/bibliographic-sources] 정보나루 호출과 응답 해석: 값 읽기, 오류 구분, 키 전달."""

import logging
from datetime import date

import httpx
import pytest

from app.central.external.data4library.client import get_books_by_isbn, raw_books_by_isbn
from app.central.external.data4library.definitions import MIN_CALL_INTERVAL_SECONDS
from app.central.external.data4library.parsing import parse_book, split_title
from app.central.external.http import RateLimiter, SourceStopped, StopReason
from tests.helpers import VALID_ISBN, VALID_ISBN_2
from tests.source_helpers import (
    TEST_D4L_KEY,
    FakeData4Library,
    d4l_book,
    d4l_error,
    d4l_not_found,
    d4l_ok,
)


async def _call(response) -> list:
    fake = FakeData4Library()
    fake.responses[VALID_ISBN] = response
    return await get_books_by_isbn(fake.client(), VALID_ISBN)


async def test_found() -> None:
    """[catalog/bibliographic-sources] 정보나루 응답 해석 (도서 상세 한 건)"""
    (book,) = await _call(d4l_ok(d4l_book(VALID_ISBN)))
    assert book.isbn13 == VALID_ISBN
    assert (book.title, book.subtitle) == ("강아지똥", "권정생 그림책")
    assert book.author == "지은이: 권정생 ;그림: 정승각"
    assert (book.kdc, book.category) == ("813.8", "문학 > 한국문학 > 동화")
    assert book.addition_symbol == "77810"
    assert book.volume is None


def test_trims_spaces() -> None:
    """[catalog/bibliographic-sources] 정보나루 응답 해석 / 앞뒤 공백"""
    assert parse_book(d4l_book(VALID_ISBN, publisher=" 창비 ")).publisher == "창비"


def test_unescapes_description() -> None:
    """[catalog/bibliographic-sources] 정보나루 응답 해석 / 이스케이프된 소개"""
    book = parse_book(d4l_book(VALID_ISBN, description="특별판 &lt;아몬드&gt; &amp; 작가의 말"))
    assert book.description == "특별판 <아몬드> & 작가의 말"


@pytest.mark.parametrize("code", ["7485", "", "7485A", "748500", None])
def test_invalid_addition_symbol(code) -> None:
    """[catalog/bibliographic-sources] 정보나루 응답 해석 / 잘못된 부가기호"""
    assert parse_book(d4l_book(VALID_ISBN, addition_symbol=code)).addition_symbol is None


def test_cover_is_not_read() -> None:
    """[catalog/bibliographic-sources] 정보나루 응답 해석 / 정보나루 표지 미사용"""
    book = parse_book(d4l_book(VALID_ISBN))
    assert not hasattr(book, "cover_url")
    assert "image.example" not in repr(book)


@pytest.mark.parametrize(
    ("value", "expected"),
    [("2017", None), ("2017-03-31", date(2017, 3, 31)), ("20170331", date(2017, 3, 31))],
)
def test_published_date(value: str, expected: date | None) -> None:
    """[catalog/bibliographic-sources] 필드별 기준 출처 / 해만 있는 출간일"""
    assert parse_book(d4l_book(VALID_ISBN, publication_date=value)).published_date == expected


def test_kdc_is_normalized() -> None:
    """[catalog/bibliographic-sources] 정보나루 응답 해석 (KDC는 분류기호 저장 규칙)"""
    assert parse_book(d4l_book(VALID_ISBN, class_no=" KDC 813.7 ")).kdc == "813.7"
    assert parse_book(d4l_book(VALID_ISBN, class_no="")).kdc is None


@pytest.mark.parametrize(
    ("bookname", "title", "subtitle"),
    [
        ("아몬드 :손원평 장편소설", "아몬드", "손원평 장편소설"),
        (
            "사피엔스 :유인원에서 사이보그까지, 인간 역사의 대담하고 위대한 질문",
            "사피엔스",
            "유인원에서 사이보그까지, 인간 역사의 대담하고 위대한 질문",
        ),
        ("시선으로부터,", "시선으로부터,", None),
        ("C++:기초", "C++:기초", None),
        ("하나 :둘 :셋", "하나", "둘 :셋"),
        ("노르웨이의 숲 =Norwegian wood", "노르웨이의 숲", None),
        ("해독 혁명 =질병 없는 몸을 위한 5단계 독소 해방 /Detox revolution", "해독 혁명", None),
        (
            "언제나 기억해 - 소년과 두더지와 여우와 말, 그리고 폭풍우",
            "언제나 기억해",
            "소년과 두더지와 여우와 말, 그리고 폭풍우",
        ),
        ("해리엇 =175년 동안 바다를 품고 살았던 거북 이야기 /Harriet", "해리엇", None),
        ("(한밤중) 달빛 식당", "한밤중 달빛 식당", None),
        (
            "(10대를 위한) 정의란 무엇인가 :마이클 샌델의 정의 수업",
            "10대를 위한 정의란 무엇인가",
            "마이클 샌델의 정의 수업",
        ),
        ("모모 :시간을 훔치는 도둑 =Momo", "모모", "시간을 훔치는 도둑"),
        ("자전거-여행", "자전거-여행", None),
    ],
)
def test_split_title(bookname: str, title: str, subtitle: str | None) -> None:
    """[catalog/bibliographic-sources] 정보나루 서명 정리 / 부제가 붙은 서명, 부제 안의 쉼표,

    대등 서명, 하이픈 부제, 괄호 관제, 나누지 않는 쌍점
    """
    assert split_title(bookname) == (title, subtitle)


@pytest.mark.parametrize(
    ("volume", "title"),
    [
        ("8", "고양이 해결사 깜냥 8"),
        ("양장", "고양이 해결사 깜냥"),
        ("1 - 4/", "고양이 해결사 깜냥"),
        ("", "고양이 해결사 깜냥"),
    ],
)
def test_volume_is_appended(volume: str, title: str) -> None:
    """[catalog/bibliographic-sources] 정보나루 서명 정리 / 권 붙이기, 숫자가 아닌 권"""
    assert split_title("고양이 해결사 깜냥", volume)[0] == title
    book = parse_book(d4l_book(VALID_ISBN, bookname="고양이 해결사 깜냥", vol=volume))
    assert book.title == title


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, json={"response": {"request": {}, "detail": []}}),
        httpx.Response(200, json={"response": {"request": {}}}),
        httpx.Response(200, json={"response": {"detail": [{"book": None}]}}),
        d4l_not_found(),
    ],
)
async def test_not_found_results(response) -> None:
    """[catalog/book-enrichment] 찾지 못한 도서 / 결과가 빈 성공 응답"""
    assert await _call(response) == []


async def test_single_detail_object() -> None:
    """[catalog/bibliographic-sources] 정보나루 응답 해석 (detail이 한 건으로 오는 꼴)"""
    body = {"response": {"detail": {"book": d4l_book(VALID_ISBN)}}}
    (book,) = await _call(httpx.Response(200, json=body))
    assert book.isbn13 == VALID_ISBN


@pytest.mark.parametrize(
    ("response", "reason"),
    [
        (httpx.Response(429), StopReason.RATE_LIMITED),
        (d4l_error("일일 호출 건수를 초과했습니다."), StopReason.RATE_LIMITED),
        (httpx.Response(401), StopReason.AUTH_FAILED),
        (d4l_error("인증정보가 일치하지 않습니다."), StopReason.AUTH_FAILED),
        (d4l_error("알 수 없는 오류"), StopReason.UPSTREAM_UNAVAILABLE),
        (httpx.Response(503), StopReason.UPSTREAM_UNAVAILABLE),
        (httpx.Response(404), StopReason.UPSTREAM_UNAVAILABLE),
        (httpx.Response(200, text="<html>"), StopReason.UPSTREAM_UNAVAILABLE),
        (httpx.Response(200, json=[]), StopReason.UPSTREAM_UNAVAILABLE),
        (httpx.Response(200, json={"response": None}), StopReason.UPSTREAM_UNAVAILABLE),
        (httpx.ReadTimeout("시간 초과"), StopReason.UPSTREAM_UNAVAILABLE),
        (httpx.ConnectError("연결 실패"), StopReason.UPSTREAM_UNAVAILABLE),
    ],
)
async def test_stop_results(response, reason: StopReason) -> None:
    """[catalog/book-enrichment] 외부 장애 시 중단 (정보나루 오류 구분)"""
    with pytest.raises(SourceStopped) as caught:
        await _call(response)
    assert caught.value.source == "data4library"
    assert caught.value.reason == reason


async def test_interval_between_calls() -> None:
    """[catalog/book-enrichment] 호출 속도 제한 / 연속 호출 간격 (정보나루 0.5초)"""
    assert MIN_CALL_INTERVAL_SECONDS == 0.5
    now = 100.0
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        nonlocal now
        waits.append(seconds)
        now += seconds

    fake = FakeData4Library()
    limiter = RateLimiter(MIN_CALL_INTERVAL_SECONDS, clock=lambda: now, sleep=sleep)
    client = fake.client(limiter)
    for isbn in (VALID_ISBN, VALID_ISBN_2, VALID_ISBN):
        await get_books_by_isbn(client, isbn)
    assert waits == [0.5, 0.5]


async def test_key_goes_in_query_only() -> None:
    """[catalog/book-enrichment] API 키 보호 / 정보나루 키"""
    fake = FakeData4Library()
    await raw_books_by_isbn(fake.client(), VALID_ISBN)
    (request,) = fake.requests
    assert request.url.params["authKey"] == TEST_D4L_KEY
    assert request.url.params["format"] == "json"
    assert TEST_D4L_KEY not in " ".join(f"{k}={v}" for k, v in request.headers.items())


@pytest.mark.parametrize(
    "response", [httpx.ConnectError("연결 실패"), httpx.Response(503), d4l_error("인증 실패")]
)
async def test_key_not_in_logs_or_errors(response, caplog: pytest.LogCaptureFixture) -> None:
    """[catalog/book-enrichment] API 키 보호 / 오류에 키 없음"""
    caplog.set_level(logging.INFO)
    with pytest.raises(SourceStopped) as caught:
        await _call(response)
    assert caught.value.__cause__ is None
    # httpx 예외(URL을 담고 있다)가 사슬로 따라오지 않는다
    assert caught.value.__context__ is None or caught.value.__suppress_context__
    assert TEST_D4L_KEY not in str(caught.value) + repr(caught.value)
    assert TEST_D4L_KEY not in caplog.text


async def test_success_request_is_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    """[catalog/book-enrichment] API 키 보호 (INFO 수준에서도 요청 URL이 로그에 없다)"""
    caplog.set_level(logging.INFO)
    await _call(d4l_ok(d4l_book(VALID_ISBN)))
    assert TEST_D4L_KEY not in caplog.text


def test_real_response_shapes() -> None:
    """[catalog/bibliographic-sources] 정보나루 응답 해석 (확인 호출로 본 꼴, 2026-11-16)

    서명 끝의 공백, 부제가 붙은 서명, 해만 있는 출간일, `지음;… 옮김`·`글·그림 ;… 옮김` 꼴 저자.
    """
    book = parse_book(
        d4l_book(
            VALID_ISBN,
            bookname="쇼펜하우어 인생수업 :한 번뿐인 삶 이렇게 살아라 ",
            authors="쇼펜하우어 저 ;김지민 엮음",
            publication_date="2024",
            class_no="165.47",
            class_nm="철학 > 서양철학 > 독일, 오스트리아철학",
            addition_symbol="03800",
        )
    )
    assert (book.title, book.subtitle) == ("쇼펜하우어 인생수업", "한 번뿐인 삶 이렇게 살아라")
    assert book.published_date is None
    assert (book.kdc, book.addition_symbol) == ("165.47", "03800")
    assert parse_book(d4l_book(VALID_ISBN, bookname="엄마가 유령이 되었어! ")).title == (
        "엄마가 유령이 되었어!"
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("헤르만 헤세 지음;박병덕 옮김", [("헤르만 헤세", "author"), ("박병덕", "translator")]),
        ("쇼펜하우어 저 ;김지민 엮음", [("쇼펜하우어", "author"), ("김지민", "editor")]),
        (
            "노부미 글·그림 ;이기웅 옮김",
            [("노부미", "author"), ("노부미", "illustrator"), ("이기웅", "translator")],
        ),
    ],
)
def test_real_author_shapes(text: str, expected: list[tuple[str, str]]) -> None:
    """[catalog/book-contributors] 출처별 해석기 (확인 호출로 본 정보나루 저자 꼴)"""
    from app.core.contributors import parse_author_text

    assert [(p.name, p.role.value) for p in parse_author_text(text)] == expected
