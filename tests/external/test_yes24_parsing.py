"""[catalog/book-enrichment] 응답 값 정규화."""

import pytest

from app.external.yes24.parsing import parse_date, parse_item, parse_price
from tests.helpers import VALID_ISBN
from tests.yes24_helpers import item


def test_empty_string_is_no_value() -> None:
    """[catalog/book-enrichment] 응답 값 정규화 / 빈 문자열"""
    assert parse_item(item(VALID_ISBN, subTitle="")).subtitle is None


def test_eight_digit_date() -> None:
    """[catalog/book-enrichment] 응답 값 정규화 / 8자리 출간일"""
    assert parse_date("19960401").isoformat() == "1996-04-01"


def test_hyphen_date() -> None:
    """[catalog/book-enrichment] 응답 값 정규화 / 하이픈 출간일"""
    assert parse_date("2013-12-24").isoformat() == "2013-12-24"


@pytest.mark.parametrize("value", ["미정", "19961301", "1996", "", None, 19960401])
def test_unreadable_date(value) -> None:
    """[catalog/book-enrichment] 응답 값 정규화 / 읽을 수 없는 출간일"""
    assert parse_date(value) is None


def test_unreadable_date_keeps_other_fields() -> None:
    """[catalog/book-enrichment] 응답 값 정규화 / 읽을 수 없는 출간일 (다른 필드는 채움)"""
    parsed = parse_item(item(VALID_ISBN, publishDate="미정"))
    assert parsed.published_date is None
    assert parsed.title == "강아지똥"


@pytest.mark.parametrize("value", [14000.0, 14000, "14000.0", "14000"])
def test_price_is_integer(value) -> None:
    """[catalog/book-enrichment] 응답 값 정규화 / 소수 표기 정가"""
    price = parse_price(value)
    assert price == 14000 and isinstance(price, int)


@pytest.mark.parametrize("value", [-1, 12.5, "가격", None, True, "NaN", 2**31])
def test_unreadable_price(value) -> None:
    """[catalog/book-enrichment] 응답 값 정규화 (읽을 수 없는 정가는 비움)"""
    assert parse_price(value) is None


def test_line_breaks() -> None:
    """[catalog/book-enrichment] 응답 값 정규화 / 줄바꿈 정리"""
    detail = {"bookIntroduction": "첫 줄\r\n둘째 줄\r셋째 줄", "tableOfContents": "1장\r\n2장"}
    parsed = parse_item(item(VALID_ISBN, contentDetail=detail))
    assert parsed.description == "첫 줄\n둘째 줄\n셋째 줄"
    assert parsed.table_of_contents == "1장\n2장"


def test_too_long_optional_field_is_empty() -> None:
    """[catalog/book-enrichment] 응답 값 정규화 (저장 길이를 넘는 선택 필드만 비움)"""
    parsed = parse_item(item(VALID_ISBN, publisher="가" * 201))
    assert parsed.publisher is None
    assert parsed.title == "강아지똥"


def test_missing_content_detail() -> None:
    """[catalog/book-enrichment] 응답 값 정규화 (contentDetail이 null이어도 읽음)"""
    assert parse_item(item(VALID_ISBN, contentDetail=None)).description is None
