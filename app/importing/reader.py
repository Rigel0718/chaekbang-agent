"""xlsx·CSV 파일을 행 목록으로 읽는다."""

import csv
import io
import zipfile
from typing import Any

from openpyxl import load_workbook

from app.importing.errors import ImportFileError

MAX_BYTES = 20 * 1024 * 1024
MAX_ROWS = 50_000

_UNSUPPORTED = "엑셀에서 xlsx나 CSV로 다시 저장해 올려 주세요"
_OLE_MAGIC = b"\xd0\xcf\x11\xe0"  # 예전 .xls


def read_table(filename: str, content: bytes) -> list[list[Any]]:
    """파일 내용을 행 목록으로 돌려준다. 읽을 수 없으면 ImportFileError."""
    if len(content) > MAX_BYTES:
        raise ImportFileError(f"파일이 너무 큽니다 (최대 {MAX_BYTES // 1024 // 1024}MB)")
    if content.startswith(_OLE_MAGIC):
        raise ImportFileError(f"예전 .xls 형식은 읽을 수 없습니다. {_UNSUPPORTED}")
    if zipfile.is_zipfile(io.BytesIO(content)):
        return _read_xlsx(content)
    if filename.lower().endswith((".csv", ".txt")):
        return _read_csv(content)
    raise ImportFileError(f"읽을 수 없는 파일입니다. {_UNSUPPORTED}")


def _limited(rows) -> list[list[Any]]:
    table: list[list[Any]] = []
    for row in rows:
        table.append(list(row))
        if len(table) > MAX_ROWS:
            raise ImportFileError(f"행이 너무 많습니다 (최대 {MAX_ROWS:,}행)")
    return table


def _read_xlsx(content: bytes) -> list[list[Any]]:
    try:
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001 - openpyxl은 깨진 파일에 여러 예외를 낸다
        raise ImportFileError(f"읽을 수 없는 파일입니다. {_UNSUPPORTED}") from exc
    try:
        return _limited(workbook.worksheets[0].iter_rows(values_only=True))
    finally:
        workbook.close()


def _decode(content: bytes) -> str:
    if b"\x00" in content:
        raise ImportFileError(f"읽을 수 없는 파일입니다. {_UNSUPPORTED}")
    for encoding in ("utf-8-sig", "cp949"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ImportFileError(f"글자 인코딩을 알 수 없는 파일입니다. {_UNSUPPORTED}")


def _read_csv(content: bytes) -> list[list[Any]]:
    text = _decode(content)
    first_line = text.split("\n", 1)[0]
    delimiter = "\t" if first_line.count("\t") > first_line.count(",") else ","
    return _limited(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))
