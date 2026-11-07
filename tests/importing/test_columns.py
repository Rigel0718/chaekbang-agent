"""[catalog/holdings-import] 필수 열과 머리글 인식, 열 직접 지정."""

import pytest

from app.library.importing.columns import find_header
from app.library.importing.errors import ImportFileError


def test_header_synonyms() -> None:
    """[catalog/holdings-import] 필수 열과 머리글 인식 / 다른 머리글 표기"""
    match = find_header([["자료번호", "도서명", "지은이"]])
    assert match.columns == {"accession_number": 0, "title": 1, "author": 2}
    assert match.mapping["author"] == "지은이"


@pytest.mark.parametrize("header", ["ISBN", "isbn", "ISBN(13)", " I S B N "])
def test_header_noise_ignored(header: str) -> None:
    """[catalog/holdings-import] 필수 열과 머리글 인식 (공백·괄호·대소문자)"""
    assert "isbn" in find_header([["등록번호", "서명", "저자", header]]).columns


def test_required_columns_only() -> None:
    """[catalog/holdings-import] 필수 열과 머리글 인식 / 필수 열만 있는 파일"""
    match = find_header([["등록번호", "서명", "저자"], ["EM1", "모모", "엔데"]])
    assert set(match.columns) == {"accession_number", "title", "author"}


def test_title_rows_above_header() -> None:
    """[catalog/holdings-import] 필수 열과 머리글 인식 / 머리글 위의 제목 줄"""
    table = [["장서 목록 (2026-11-01)"], [], ["등록번호", "서명", "저자"], ["EM1", "모모", "엔데"]]
    assert find_header(table).row_index == 2


def test_missing_required_column() -> None:
    """[catalog/holdings-import] 필수 열과 머리글 인식 / 필수 열 없음"""
    with pytest.raises(ImportFileError) as caught:
        find_header([["등록번호", "서명", "비고"]])
    assert caught.value.extra == {"missing": ["저자"], "headers": ["등록번호", "서명", "비고"]}


def test_override_unknown_header() -> None:
    """[catalog/holdings-import] 열 직접 지정 / 인식하지 못한 머리글 지정"""
    match = find_header([["등록번호", "서명", "책임표시"]], {"author": "책임표시"})
    assert match.columns["author"] == 2


def test_override_beats_auto() -> None:
    """[catalog/holdings-import] 열 직접 지정 (지정한 열이 자동 인식보다 우선)"""
    match = find_header([["등록번호", "서명", "저자", "역자"]], {"author": "역자"})
    assert match.columns["author"] == 3


def test_override_unknown_field() -> None:
    """[catalog/holdings-import] 열 직접 지정 (모르는 표준 열)"""
    with pytest.raises(ImportFileError, match="모르는 표준 열"):
        find_header([["등록번호", "서명", "저자"]], {"borrower": "대출자"})


@pytest.mark.parametrize("header", ["대출자", "대출자명", "이용자", "연락처", "회원번호", "비고"])
def test_personal_columns_not_recognized(header: str) -> None:
    """[catalog/holdings-import] 인식하지 못한 열은 저장하지 않음 (개인정보 열은 표준 열이 아님)"""
    match = find_header([["등록번호", "서명", "저자", header]])
    assert 3 not in match.columns.values()
