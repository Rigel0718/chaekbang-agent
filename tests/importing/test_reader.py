"""[catalog/holdings-import] 파일 형식."""

import io

import pytest
from openpyxl import Workbook

from app.library.importing import reader
from app.library.importing.errors import ImportFileError
from app.library.importing.reader import read_table


def _xlsx(rows: list[list]) -> bytes:
    book = Workbook()
    for row in rows:
        book.active.append(row)
    book.create_sheet("둘째 시트").append(["무시", "됩니다"])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_cp949_csv() -> None:
    """[catalog/holdings-import] 파일 형식 / CP949 CSV"""
    content = "등록번호,서명,저자\nEM1,마당을 나온 암탉,황선미\n".encode("cp949")
    assert read_table("a.csv", content)[1] == ["EM1", "마당을 나온 암탉", "황선미"]


def test_utf8_csv_with_bom() -> None:
    """[catalog/holdings-import] 파일 형식 (UTF-8 BOM)"""
    content = "등록번호,서명\nEM1,모모\n".encode("utf-8-sig")
    assert read_table("a.csv", content)[0] == ["등록번호", "서명"]


def test_tab_separated() -> None:
    """[catalog/holdings-import] 파일 형식 (탭으로 나뉜 내보내기)"""
    assert read_table("a.txt", "등록번호\t서명\n".encode())[0] == ["등록번호", "서명"]


def test_xlsx_first_sheet() -> None:
    """[catalog/holdings-import] 파일 형식 / xlsx 파일"""
    table = read_table("a.xlsx", _xlsx([["등록번호", "서명"], ["EM1", "모모"]]))
    assert table == [["등록번호", "서명"], ["EM1", "모모"]]


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("old.xls", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 64),
        ("broken.xlsx", b"PK\x03\x04 not really a zip"),
        ("broken.csv", b"\x00\x01\x02\x03"),
        ("image.png", b"\x89PNG\r\n"),
    ],
)
def test_unsupported(name: str, content: bytes) -> None:
    """[catalog/holdings-import] 파일 형식 / 지원하지 않는 형식"""
    with pytest.raises(ImportFileError, match="xlsx나 CSV"):
        read_table(name, content)


def test_size_and_row_limits(monkeypatch: pytest.MonkeyPatch) -> None:
    """[catalog/holdings-import] 파일 형식 (크기·행 수 상한)"""
    monkeypatch.setattr(reader, "MAX_BYTES", 10)
    with pytest.raises(ImportFileError, match="너무 큽니다"):
        read_table("a.csv", b"x" * 11)
    monkeypatch.setattr(reader, "MAX_BYTES", 1000)
    monkeypatch.setattr(reader, "MAX_ROWS", 2)
    with pytest.raises(ImportFileError, match="행이 너무 많습니다"):
        read_table("a.csv", b"a\nb\nc\n")
