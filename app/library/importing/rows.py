"""파일 행 → 정규화한 행. 인식한 표준 열의 값만 남는다."""

from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from app.library.importing.columns import LABELS, REQUIRED, HeaderMatch
from app.library.importing.normalize import (
    clean_text,
    normalize_cell_isbn,
    parse_acquisition,
    parse_date,
    parse_price,
    parse_status,
)
from app.library.models.catalog import AcquisitionType

MAX_LENGTHS = {
    "accession_number": 50,
    "title": 500,
    "author": 300,
    "publisher": 200,
    "call_number": 100,
    "shelf_location": 100,
    "donor": 200,
    "kdc": 20,
}

FLAG_INVALID_ISBN = "invalid_isbn"
FLAG_UNKNOWN_STATUS = "unknown_status"
FLAG_NO_ISBN = "purchased_without_isbn"
FLAG_NO_PRICE = "purchased_without_price"


@dataclass
class ParsedRow:
    row_no: int  # 파일의 줄 번호 (1부터)
    accession_number: str | None = None
    title: str | None = None
    author: str | None = None
    isbn: str | None = None
    publisher: str | None = None
    published_date: str | None = None  # ISO 날짜. JSONB에 그대로 저장한다
    call_number: str | None = None
    shelf_location: str | None = None
    kdc: str | None = None
    status: str | None = None
    acquisition: str | None = None  # 알 수 없으면 None. 적용 때 기존 값이나 unknown이 된다
    price: int | None = None
    donor: str | None = None
    separate_mark: str | None = None  # 파일 값 그대로. 뜻은 기관 개별 기능이 해석한다
    addition_code: str | None = None
    skip_reason: str | None = None
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def acquisition_flags(
    acquisition: AcquisitionType | None, has_isbn: bool, has_price: bool
) -> list[str]:
    """매입인데 빠진 정보가 있으면 오류가 아니라 표기로 남긴다. 기증처 없는 기증은 정상이다."""
    if acquisition != AcquisitionType.PURCHASED:
        return []
    flags = []
    if not has_isbn:
        flags.append(FLAG_NO_ISBN)
    if not has_price:
        flags.append(FLAG_NO_PRICE)
    return flags


def _cell(row: list[Any], match: HeaderMatch, name: str) -> Any:
    index = match.columns.get(name)
    return row[index] if index is not None and index < len(row) else None


def parse_row(row_no: int, row: list[Any], match: HeaderMatch) -> ParsedRow:
    parsed = ParsedRow(row_no=row_no)
    for name in (
        "accession_number",
        "title",
        "author",
        "publisher",
        "call_number",
        "shelf_location",
        "kdc",
        "donor",
    ):
        setattr(parsed, name, clean_text(_cell(row, match, name)))

    parsed.isbn, invalid_isbn = normalize_cell_isbn(_cell(row, match, "isbn"))
    if invalid_isbn:
        parsed.flags.append(FLAG_INVALID_ISBN)

    published: date | None = parse_date(_cell(row, match, "published_date"))
    parsed.published_date = published.isoformat() if published else None

    status, unknown_status = parse_status(clean_text(_cell(row, match, "status")))
    parsed.status = status.value if status else None
    if unknown_status:
        parsed.flags.append(FLAG_UNKNOWN_STATUS)

    acquisition = parse_acquisition(clean_text(_cell(row, match, "acquisition")))
    if acquisition is None and parsed.donor is not None:
        acquisition = AcquisitionType.DONATED
    parsed.acquisition = acquisition.value if acquisition else None
    if acquisition == AcquisitionType.PURCHASED:
        parsed.price = parse_price(_cell(row, match, "price"))
        parsed.donor = None  # 매입 사본에는 기증처를 두지 않는다
    # 그 밖의 사본에서 가격 열은 정가일 수 있어 쓰지 않는다.

    parsed.separate_mark = clean_text(_cell(row, match, "separate_mark"))
    parsed.addition_code = clean_text(_cell(row, match, "addition_code"))

    missing = [LABELS[name] for name in REQUIRED if getattr(parsed, name) is None]
    if missing:
        parsed.skip_reason = f"필수 값이 없습니다: {', '.join(missing)}"
        return parsed
    too_long = [
        LABELS[name]
        for name, limit in MAX_LENGTHS.items()
        if len(getattr(parsed, name) or "") > limit
    ]
    if too_long:
        parsed.skip_reason = f"값이 너무 깁니다: {', '.join(too_long)}"
    return parsed


def parse_rows(table: list[list[Any]], match: HeaderMatch) -> list[ParsedRow]:
    """머리글 아래 행을 정규화한다. 빈 행은 없는 것으로 치고, 파일 안의 중복 등록번호는 건너뛴다."""
    rows: list[ParsedRow] = []
    seen: set[str] = set()
    for index in range(match.row_index + 1, len(table)):
        row = table[index]
        if all(clean_text(cell) is None for cell in row):
            continue
        parsed = parse_row(index + 1, row, match)
        accession = parsed.accession_number
        if parsed.skip_reason is None and accession in seen:
            parsed.skip_reason = f"파일 안에서 등록번호가 겹칩니다: {accession}"
        if accession:
            seen.add(accession)
        rows.append(parsed)
    return rows
