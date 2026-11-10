"""[catalog/holdings-import] ISBN 정규화, 표기 변환."""

from datetime import date

import pytest

from app.library.importing.normalize import (
    clean_text,
    normalize_cell_isbn,
    parse_acquisition,
    parse_date,
    parse_price,
    parse_status,
)
from app.library.models.catalog import AcquisitionType, HoldingStatus


def test_isbn10() -> None:
    """[catalog/holdings-import] ISBN 정규화 / ISBN-10"""
    assert normalize_cell_isbn("0-8044-2957-X") == ("9780804429573", False)
    assert normalize_cell_isbn("0804429 57x") == ("9780804429573", False)


@pytest.mark.parametrize("value", [9780306406157, 9780306406157.0, "9780306406157.0"])
def test_excel_number_cell(value) -> None:
    """[catalog/holdings-import] ISBN 정규화 / 엑셀 숫자 셀"""
    assert normalize_cell_isbn(value) == ("9780306406157", False)


def test_hyphens() -> None:
    """[catalog/holdings-import] ISBN 정규화 (하이픈)"""
    assert normalize_cell_isbn("978-0-306-40615-7") == ("9780306406157", False)


@pytest.mark.parametrize("value", ["9780306406158", "0804429571", "12345", "9.78E+12", "없음"])
def test_invalid_isbn(value: str) -> None:
    """[catalog/holdings-import] ISBN 정규화 / 잘못된 ISBN"""
    assert normalize_cell_isbn(value) == (None, True)


@pytest.mark.parametrize("value", [None, "", "   "])
def test_empty_isbn(value) -> None:
    """[catalog/holdings-import] ISBN 정규화 (빈 칸은 잘못된 값이 아님)"""
    assert normalize_cell_isbn(value) == (None, False)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("대출중", HoldingStatus.ON_LOAN),
        ("대출 중", HoldingStatus.ON_LOAN),
        ("대출가능", HoldingStatus.AVAILABLE),
        ("비치", HoldingStatus.AVAILABLE),
        ("분실", HoldingStatus.LOST),
        ("파손", HoldingStatus.DAMAGED),
        ("제적", HoldingStatus.WITHDRAWN),
    ],
)
def test_status_labels(value: str, expected: HoldingStatus) -> None:
    """[catalog/holdings-import] 사본 값 반영 (대출 상태 표기 변환)"""
    assert parse_status(value) == (expected, False)


def test_unknown_status_label() -> None:
    """[catalog/holdings-import] 사본 값 반영 (알 수 없는 표기)"""
    assert parse_status("수리중") == (None, True)
    assert parse_status(None) == (None, False)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("구입", AcquisitionType.PURCHASED),
        ("납품", AcquisitionType.PURCHASED),
        ("기증", AcquisitionType.DONATED),
        ("수증", AcquisitionType.DONATED),
        ("교환", None),
        (None, None),
    ],
)
def test_acquisition_labels(value, expected) -> None:
    """[catalog/holdings-import] 입수 구분 인식 (수입구분 표기 변환)"""
    assert parse_acquisition(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("15,000", 15000),
        ("15000원", 15000),
        (15000, 15000),
        (15000.0, 15000),
        ("15000.0", 15000),
        ("", None),
        ("-100", None),
        ("13000.5", None),
        (13000.5, None),
        (None, None),
    ],
)
def test_price(value, expected) -> None:
    """가격 칸을 원 단위 정수로 읽는다. float로 남기지 않는다."""
    assert parse_price(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2020-03-15", date(2020, 3, 15)),
        ("2020.3.15", date(2020, 3, 15)),
        ("20200315", date(2020, 3, 15)),
        ("2020", None),
        ("2020-13-01", None),
    ],
)
def test_date(value, expected) -> None:
    """연도만 있으면 날짜를 지어내지 않는다."""
    assert parse_date(value) == expected


def test_clean_text() -> None:
    assert clean_text("  마을   이야기 ") == "마을 이야기"
    assert clean_text(12345.0) == "12345"
    assert clean_text("  ") is None


def test_clean_text_spaces() -> None:
    """[catalog/holdings-import] 셀 값 정리 (줄바꿈 없는 공백, 보이지 않는 글자)"""
    assert clean_text("  공룡\u00a0 백과\u200b ") == "공룡 백과"
    assert clean_text("\ufeff") is None


def test_status_label_spaces() -> None:
    """[catalog/holdings-import] 대출 상태 표기 (공백 종류와 상관없이 인식)"""
    assert parse_status("대출\u00a0가능") == (HoldingStatus.AVAILABLE, False)
