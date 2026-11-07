"""표준 열 정의와 머리글 인식.

필수 열은 등록번호, 서명, 저자뿐이다. 나머지는 있으면 쓰고 없으면 넘어간다.
동의어는 정리한 머리글과 완전히 일치할 때만 인식한다. 부분 일치를 쓰면 `대출자`가
`대출상태`로 잡히는 것처럼 개인정보 열이 들어올 수 있다.
"""

import re
from dataclasses import dataclass
from typing import Any

from app.importing.errors import ImportFileError

REQUIRED = ("accession_number", "title", "author")

LABELS = {
    "accession_number": "등록번호",
    "title": "서명",
    "author": "저자",
    "isbn": "ISBN",
    "publisher": "출판사",
    "published_date": "발행일",
    "call_number": "청구기호",
    "separate_mark": "별치기호",
    "shelf_location": "자료실",
    "status": "대출 상태",
    "acquisition": "수입구분",
    "price": "가격",
    "donor": "기증처",
    "kdc": "분류기호",
    "addition_code": "부가기호",
}

SYNONYMS: dict[str, tuple[str, ...]] = {
    "accession_number": ("등록번호", "자료번호", "바코드", "바코드번호", "등록번호바코드"),
    "title": ("서명", "도서명", "자료명", "제목", "책제목", "표제", "표제명"),
    "author": ("저자", "저자명", "지은이", "저작자", "작가", "저자사항"),
    "isbn": ("isbn", "isbn13", "isbn번호", "국제표준도서번호"),
    "publisher": ("출판사", "출판사명", "발행자", "발행처", "출판자"),
    "published_date": ("발행일", "출간일", "출판일", "발행일자"),
    "call_number": ("청구기호", "청구번호"),
    "separate_mark": ("별치기호", "별치", "별치구분"),
    "shelf_location": ("자료실", "자료실명", "소장위치", "배가위치", "서가위치", "위치"),
    "status": ("대출상태", "자료상태", "상태", "소장상태", "대출여부"),
    "acquisition": ("수입구분", "입수구분", "구입구분", "수서구분", "입수방법", "수입방법"),
    "price": ("가격", "구입가", "구입가격", "정가", "도서가격", "금액"),
    "donor": ("기증처", "기증자", "기증기관", "기증인"),
    "kdc": ("분류기호", "kdc", "분류번호", "kdc분류기호"),
    "addition_code": ("부가기호", "isbn부가기호"),
}

_HEADER_NOISE = re.compile(r"[\s()\[\]{}·_\-/.:]")
_BY_HEADER = {name: field for field, names in SYNONYMS.items() for name in names}
HEADER_SEARCH_ROWS = 20


@dataclass(frozen=True)
class HeaderMatch:
    row_index: int  # 0부터 센 머리글 행
    columns: dict[str, int]  # 표준 열 → 열 위치
    mapping: dict[str, str]  # 표준 열 → 파일의 머리글 (기록용)


def clean_header(value: Any) -> str:
    return _HEADER_NOISE.sub("", str(value or "")).casefold()


def _match(row: list[Any], overrides: dict[str, str]) -> tuple[dict[str, int], dict[str, str]]:
    wanted = {clean_header(header): field for field, header in overrides.items()}
    columns: dict[str, int] = {}
    mapping: dict[str, str] = {}
    for index, cell in enumerate(row):
        if cell is None or str(cell).strip() == "":
            continue
        key = clean_header(cell)
        field = wanted.get(key) or _BY_HEADER.get(key)
        # 직접 지정한 필드는 자동 인식으로 덮어쓰지 않는다. 같은 열이 둘이면 앞의 것을 쓴다.
        if field is None or field in columns:
            continue
        if field in overrides and key != clean_header(overrides[field]):
            continue
        columns[field] = index
        mapping[field] = str(cell).strip()
    return columns, mapping


def find_header(table: list[list[Any]], overrides: dict[str, str] | None = None) -> HeaderMatch:
    """앞쪽 행에서 필수 열을 가장 많이 찾은 첫 행을 머리글로 쓴다.

    overrides는 {표준 열: 파일의 머리글}이고 자동 인식보다 우선한다.
    필수 열을 다 찾지 못하면 ImportFileError (찾지 못한 열과 파일의 머리글을 담는다).
    """
    overrides = overrides or {}
    unknown = sorted(set(overrides) - set(SYNONYMS))
    if unknown:
        raise ImportFileError(f"모르는 표준 열입니다: {', '.join(unknown)}")

    best: tuple[int, int, dict[str, int], dict[str, str]] | None = None
    for index, row in enumerate(table[:HEADER_SEARCH_ROWS]):
        columns, mapping = _match(row, overrides)
        score = sum(field in columns for field in REQUIRED)
        if score and (best is None or score > best[0]):
            best = (score, index, columns, mapping)

    if best is not None and best[0] == len(REQUIRED):
        return HeaderMatch(row_index=best[1], columns=best[2], mapping=best[3])

    found = best[2] if best else {}
    missing = [LABELS[field] for field in REQUIRED if field not in found]
    source_row = table[best[1]] if best else next((r for r in table if any(r)), [])
    headers = [str(cell).strip() for cell in source_row if cell not in (None, "")]
    raise ImportFileError(
        f"필수 열을 찾지 못했습니다: {', '.join(missing)}", missing=missing, headers=headers
    )
