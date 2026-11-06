"""정답이 붙은 가상 내보내기 파일. 같은 seed면 같은 파일이 만들어진다."""

import csv
import io
import random
from dataclasses import dataclass

from openpyxl import Workbook

from app.core.isbn import isbn13_check_digit

ROWS_PER_FILE = 200
CHILDREN_RATE = 0.3
INVALID_ISBN_RATE = 0.03
NO_ISBN_RATE = 0.1


@dataclass(frozen=True)
class Truth:
    """행 하나의 정답."""

    accession_number: str
    isbn: str | None  # 올바른 ISBN. 없거나 일부러 틀린 값이면 None
    invalid_isbn: bool  # 파일에 틀린 ISBN을 넣은 행
    children: bool


@dataclass(frozen=True)
class EvalFile:
    name: str
    filename: str
    content: bytes
    truth: list[Truth]
    has_children_signal: bool  # 어린이 근거 열이 있는 파일


def _isbn13(rng: random.Random) -> str:
    first12 = f"978{rng.randrange(10**9):09d}"
    return first12 + isbn13_check_digit(first12)


def _isbn10_of(isbn13: str) -> str:
    body = isbn13[3:12]
    total = sum(int(d) * (10 - i) for i, d in enumerate(body))
    check = (11 - total % 11) % 11
    return body + ("X" if check == 10 else str(check))


def _hyphenated(isbn13: str) -> str:
    return f"{isbn13[:3]}-{isbn13[3:5]}-{isbn13[5:9]}-{isbn13[9:12]}-{isbn13[12]}"


def _truths(rng: random.Random, prefix: str) -> list[Truth]:
    truths = []
    for n in range(ROWS_PER_FILE):
        roll = rng.random()
        invalid = roll < INVALID_ISBN_RATE
        missing = INVALID_ISBN_RATE <= roll < INVALID_ISBN_RATE + NO_ISBN_RATE
        truths.append(
            Truth(
                accession_number=f"{prefix}{n:05d}",
                isbn=None if invalid or missing else _isbn13(rng),
                invalid_isbn=invalid,
                children=rng.random() < CHILDREN_RATE,
            )
        )
    return truths


def _bad_isbn(rng: random.Random) -> str:
    good = _isbn13(rng)
    return good[:12] + str((int(good[12]) + 1) % 10)


def _csv(rows: list[list], encoding: str) -> bytes:
    buffer = io.StringIO()
    csv.writer(buffer).writerows(rows)
    return buffer.getvalue().encode(encoding)


def _xlsx(rows: list[list]) -> bytes:
    book = Workbook()
    for row in rows:
        book.active.append(row)
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def _xlsx_export(rng: random.Random) -> EvalFile:
    """머리글이 표준에 가깝고 ISBN이 엑셀 숫자 셀인 파일. 별치기호로 어린이를 표시한다."""
    truths = _truths(rng, "EM")
    rows: list[list] = [
        [
            "등록번호",
            "서명",
            "저자",
            "발행자",
            "ISBN",
            "청구기호",
            "별치기호",
            "대출상태",
            "수입구분",
            "가격",
        ]
    ]
    for n, t in enumerate(truths):
        isbn: object = int(t.isbn) if t.isbn else (_bad_isbn(rng) if t.invalid_isbn else None)
        mark = rng.choice(["아", "어린이", "J"]) if t.children else rng.choice([None, "참", "향토"])
        status = rng.choice(["대출가능", "대출중", "비치"])
        acquisition = rng.choice(["구입", "구입", "기증"])
        price = 12000 if acquisition == "구입" and rng.random() < 0.9 else None
        rows.append(
            [t.accession_number, f"책 {n}", f"저자 {n}", "가람책", isbn, f"813-{n}", mark, status,
             acquisition, price]
        )  # fmt: skip
    return EvalFile("xlsx, 숫자 ISBN, 별치기호", "export.xlsx", _xlsx(rows), truths, True)


def _utf8_export(rng: random.Random) -> EvalFile:
    """머리글이 다르고 ISBN에 하이픈이 있는 파일. 자료실로 어린이를 표시한다."""
    truths = _truths(rng, "BC")
    rows: list[list] = [["자료번호", "도서명", "지은이", "ISBN", "자료실", "상태", "대출자"]]
    for n, t in enumerate(truths):
        isbn = _hyphenated(t.isbn) if t.isbn else (_bad_isbn(rng) if t.invalid_isbn else "")
        shelf = "어린이자료실" if t.children else rng.choice(["일반자료실", "종합자료실"])
        rows.append([t.accession_number, f"책 {n}", f"저자 {n}", isbn, shelf, "대출가능", "홍길순"])
    return EvalFile(
        "UTF-8 CSV, 하이픈 ISBN, 자료실", "export.csv", _csv(rows, "utf-8-sig"), truths, True
    )


def _cp949_export(rng: random.Random) -> EvalFile:
    """제목 줄이 있고 ISBN 일부가 ISBN-10인 CP949 파일. 부가기호로 어린이를 표시한다."""
    truths = _truths(rng, "SM")
    rows: list[list] = [
        ["장서 목록"],
        [],
        ["바코드", "제목", "저자명", "ISBN", "부가기호", "입수구분", "기증처"],
    ]
    for n, t in enumerate(truths):
        isbn = t.isbn or (_bad_isbn(rng) if t.invalid_isbn else "")
        if t.isbn and rng.random() < 0.5:
            isbn = _isbn10_of(t.isbn)
        code = "77810" if t.children else rng.choice(["03810", "43810", ""])
        acquisition, donor = rng.choice([("구입", ""), ("기증", ""), ("", "주민 기증"), ("", "")])
        rows.append([t.accession_number, f"책 {n}", f"저자 {n}", isbn, code, acquisition, donor])
    return EvalFile(
        "CP949 CSV, ISBN-10, 부가기호", "export2.csv", _csv(rows, "cp949"), truths, True
    )


def _minimal_export(rng: random.Random) -> EvalFile:
    """필수 열만 있는 파일. 어린이 근거가 없어 모두 일반 도서가 된다."""
    truths = [Truth(t.accession_number, None, False, t.children) for t in _truths(rng, "MN")]
    rows: list[list] = [["등록번호", "서명", "저자"]]
    rows += [[t.accession_number, f"책 {n}", f"저자 {n}"] for n, t in enumerate(truths)]
    return EvalFile("필수 열만", "minimal.csv", _csv(rows, "utf-8"), truths, False)


def generate_files(seed: int = 20261106) -> list[EvalFile]:
    rng = random.Random(seed)
    return [_xlsx_export(rng), _utf8_export(rng), _cp949_export(rng), _minimal_export(rng)]
