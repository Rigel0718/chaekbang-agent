"""가상 파일을 해석해 지표를 계산한다. DB를 쓰지 않는다."""

from dataclasses import dataclass

from app.importing.columns import find_header
from app.importing.reader import read_table
from app.importing.rows import FLAG_INVALID_ISBN, ParsedRow, acquisition_flags, parse_rows
from app.models.catalog import AcquisitionType
from evals.holdings_import.files import EvalFile


@dataclass(frozen=True)
class FileScore:
    name: str
    rows: int
    skipped: int
    isbn_recognition: float | None  # 올바른 ISBN 중 맞게 인식한 비율
    invalid_flagged: float | None  # 틀린 ISBN 중 표기한 비율
    children_precision: float | None  # 어린이로 분류한 책 중 실제 어린이 도서 비율
    children_recall: float | None  # 어린이 도서 중 어린이로 분류한 비율
    flagged_rate: float  # 표기가 하나라도 있는 행의 비율


def _ratio(hit: int, total: int) -> float | None:
    return hit / total if total else None


def _row_flags(row: ParsedRow) -> list[str]:
    acquisition = AcquisitionType(row.acquisition) if row.acquisition else None
    return row.flags + acquisition_flags(acquisition, bool(row.isbn), row.price is not None)


def score_file(file: EvalFile) -> FileScore:
    table = read_table(file.filename, file.content)
    rows = parse_rows(table, find_header(table))
    parsed = {row.accession_number: row for row in rows}
    pairs = [(t, parsed[t.accession_number]) for t in file.truth]

    with_isbn = [(t, r) for t, r in pairs if t.isbn]
    invalid = [r for t, r in pairs if t.invalid_isbn]
    predicted = [(t, r) for t, r in pairs if r.children]
    actual = [(t, r) for t, r in pairs if t.children]
    return FileScore(
        name=file.name,
        rows=len(rows),
        skipped=sum(r.skip_reason is not None for r in rows),
        isbn_recognition=_ratio(sum(t.isbn == r.isbn for t, r in with_isbn), len(with_isbn)),
        invalid_flagged=_ratio(sum(FLAG_INVALID_ISBN in r.flags for r in invalid), len(invalid)),
        children_precision=_ratio(sum(t.children for t, _ in predicted), len(predicted)),
        children_recall=_ratio(sum(r.children for _, r in actual), len(actual)),
        flagged_rate=sum(bool(_row_flags(r)) for r in rows) / len(rows),
    )
