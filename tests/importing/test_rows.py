"""[catalog/holdings-import] 행 분류, 입수 구분 인식."""

from app.importing.columns import find_header
from app.importing.rows import (
    FLAG_INVALID_ISBN,
    FLAG_NO_ISBN,
    FLAG_NO_PRICE,
    FLAG_UNKNOWN_STATUS,
    acquisition_flags,
    parse_rows,
)
from app.models.catalog import AcquisitionType

HEADER = ["등록번호", "서명", "저자", "ISBN", "수입구분", "가격", "기증처", "대출상태"]


def _parse(*rows: list):
    table = [HEADER, *rows]
    return parse_rows(table, find_header(table))


def test_blank_author_skipped() -> None:
    """[catalog/holdings-import] 행 분류 / 저자가 빈 행"""
    rows = _parse(["EM1", "모모", ""], ["EM2", "모모", "엔데"])
    assert "저자" in rows[0].skip_reason
    assert rows[1].skip_reason is None


def test_duplicate_accession_skipped() -> None:
    """[catalog/holdings-import] 행 분류 / 파일 안의 등록번호 중복"""
    rows = _parse(["EM1", "모모", "엔데"], ["EM1", "다른 책", "다른 저자"])
    assert rows[0].skip_reason is None
    assert "겹칩니다" in rows[1].skip_reason


def test_blank_lines_ignored() -> None:
    """[catalog/holdings-import] 행 분류 (빈 행은 없는 것으로 친다)"""
    rows = _parse(["EM1", "모모", "엔데"], ["", None, " "], ["EM2", "모모", "엔데"])
    assert [r.row_no for r in rows] == [2, 4]


def test_too_long_value_skipped() -> None:
    """[catalog/holdings-import] 행 분류 (저장할 수 없을 만큼 긴 값)"""
    assert "너무 깁니다" in _parse(["E" * 51, "모모", "엔데"])[0].skip_reason


def test_flags_on_row() -> None:
    """[catalog/holdings-import] ISBN 정규화 / 잘못된 ISBN (행을 버리지 않음)"""
    row = _parse(["EM1", "모모", "엔데", "9780306406158", "", "", "", "수리중"])[0]
    assert row.skip_reason is None
    assert row.isbn is None
    assert row.flags == [FLAG_INVALID_ISBN, FLAG_UNKNOWN_STATUS]


def test_no_acquisition_columns_is_unresolved() -> None:
    """[catalog/holdings-import] 입수 구분 인식 / 입수 구분 열이 없는 파일 (행 단계에서는 미정)"""
    table = [["등록번호", "서명", "저자", "가격"], ["EM1", "모모", "엔데", "9000"]]
    row = parse_rows(table, find_header(table))[0]
    assert row.acquisition is None
    assert row.price is None  # 매입이 아니면 가격 열을 쓰지 않는다


def test_donor_means_donated() -> None:
    """[catalog/holdings-import] 입수 구분 인식 (기증처가 있으면 기증)"""
    row = _parse(["EM1", "모모", "엔데", "", "", "", "주민 기증", ""])[0]
    assert (row.acquisition, row.donor) == ("donated", "주민 기증")


def test_purchased_price_used() -> None:
    """[catalog/holdings-import] 입수 구분 인식 (가격은 매입 사본의 구입가로만)"""
    assert _parse(["EM1", "모모", "엔데", "", "구입", "12,000", "", ""])[0].price == 12000
    assert _parse(["EM2", "모모", "엔데", "", "기증", "12,000", "", ""])[0].price is None


def test_acquisition_flags() -> None:
    """[catalog/holdings-import] 입수 구분 인식 / 기증처 없는 기증 사본 (표기 표)"""
    purchased, donated = AcquisitionType.PURCHASED, AcquisitionType.DONATED
    assert acquisition_flags(purchased, False, False) == [FLAG_NO_ISBN, FLAG_NO_PRICE]
    assert acquisition_flags(purchased, True, True) == []
    assert acquisition_flags(donated, False, False) == []
    assert acquisition_flags(AcquisitionType.UNKNOWN, False, False) == []
