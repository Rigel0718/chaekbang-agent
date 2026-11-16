"""실험 장서의 출처끼리 같은 ISBN의 값을 비교한다: uv run python -m evals.collection.compare

YES24 원본 파일과 새 출처 파일(`sources.py`)을 읽어 건수만 출력한다. 서명·소개 같은 값은 출력하지
않는다. DB와 외부 호출이 없다.

- 찾은 출처: 셋 다, 정보나루 없음, 카카오 없음, 정보나루·카카오 모두 없음, 아직 받지 않음
- 서명 일치: 판본 표기를 지운 서명의 `match_key`가 같은 책 수(출처 쌍마다, 둘 다 있는 책 중)
- 지은이: 지은이 키 집합이 YES24와 같은 책 수, 다른 음역 의심(지은이 수는 같고 키가 다른 책)
- 소개: 출처마다 있는 책 수와 길이 사분위
- KDC·부가기호가 있는 책 수, 어린이 구분(YES24 분류만 / 부가기호만 / 둘 중 하나)
"""

import json
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.central.external.data4library.parsing import Data4LibraryRecord, parse_book
from app.central.external.kakao.parsing import KakaoRecord, parse_document
from app.central.external.yes24.contributors import parse_yes24_author
from app.central.external.yes24.parsing import Yes24Item, parse_item
from app.core.contributors import parse_author_text, writer_keys
from app.core.isbn import normalize_isbn
from app.core.text import match_key, strip_edition
from app.features.children.rules import is_children_addition_code, is_children_category
from evals.collection.fetch import DATA_FILE as YES24_FILE
from evals.collection.sources import FOUND, SOURCES_FILE


@dataclass(frozen=True)
class Book:
    isbn: str
    yes24: Yes24Item | None
    d4l: Data4LibraryRecord | None
    kakao: KakaoRecord | None
    d4l_pending: bool
    kakao_pending: bool


def _pick[T](isbn: str, records: list[T]) -> T | None:
    return next((r for r in records if getattr(r, "isbn13", None) == isbn), None)


def load_books(yes24_path: Path = YES24_FILE, sources_path: Path = SOURCES_FILE) -> list[Book]:
    yes24_rows = json.loads(yes24_path.read_text(encoding="utf-8"))["books"]
    yes24 = {}
    for row in yes24_rows:
        parsed = parse_item(row["item"])
        yes24[normalize_isbn(parsed.isbn13 or "")] = parsed
    sources = {
        row["isbn"]: row for row in json.loads(sources_path.read_text(encoding="utf-8"))["books"]
    }
    books = []
    for isbn in sorted(yes24):
        row = sources.get(isbn, {})
        d4l_entry, kakao_entry = row.get("data4library"), row.get("kakao")
        d4l = [parse_book(b) for b in (d4l_entry or {}).get("books", [])]
        kakao = [parse_document(d) for d in (kakao_entry or {}).get("documents", [])]
        books.append(
            Book(
                isbn=isbn,
                yes24=yes24[isbn],
                d4l=_pick(isbn, d4l) if d4l_entry and d4l_entry["status"] == FOUND else None,
                kakao=_pick(isbn, kakao)
                if kakao_entry and kakao_entry["status"] == FOUND
                else None,
                d4l_pending=d4l_entry is None,
                kakao_pending=kakao_entry is None,
            )
        )
    return books


def _title_key(title: str | None) -> str | None:
    return match_key(strip_edition(title)) if title else None


def _writers(source: str, author: str | None) -> set[str]:
    if not author:
        return set()
    people = parse_yes24_author(author) if source == "yes24" else parse_author_text(author)
    return set(writer_keys(people))


def _quartiles(lengths: list[int]) -> tuple[int, int, int] | None:
    if len(lengths) < 2:
        return None
    q = statistics.quantiles(lengths, n=4)
    return round(q[0]), round(q[1]), round(q[2])


def summarize(books: list[Book]) -> dict[str, Any]:
    found = Counter()
    for b in books:
        if b.d4l_pending or b.kakao_pending:
            found["아직 받지 않음"] += 1
        elif b.d4l and b.kakao:
            found["셋 다"] += 1
        elif not b.d4l and not b.kakao:
            found["정보나루·카카오 모두 없음"] += 1
        elif not b.d4l:
            found["정보나루 없음"] += 1
        else:
            found["카카오 없음"] += 1

    titles = {}
    pairs = (("정보나루", "d4l"), ("YES24", "yes24"), ("카카오", "kakao"))
    for i, (name_a, a) in enumerate(pairs):
        for name_b, b in pairs[i + 1 :]:
            both = [x for x in books if getattr(x, a) and getattr(x, b)]
            same = sum(
                1
                for x in both
                if _title_key(getattr(x, a).title) == _title_key(getattr(x, b).title)
            )
            titles[f"{name_a}-{name_b}"] = (same, len(both))

    writers = {}
    for name, attr in (("정보나루", "d4l"), ("카카오", "kakao")):
        both = [x for x in books if x.yes24 and getattr(x, attr)]
        same = other = 0
        for x in both:
            ours = _writers(attr, getattr(x, attr).author)
            theirs = _writers("yes24", x.yes24.author)
            if ours == theirs:
                same += 1
            elif len(ours) == len(theirs):
                other += 1
        writers[name] = {"같음": same, "다른 음역 의심": other, "비교": len(both)}

    descriptions = {}
    for name, attr in (("YES24", "yes24"), ("정보나루", "d4l"), ("카카오", "kakao")):
        lengths = [
            len(getattr(x, attr).description)
            for x in books
            if getattr(x, attr) and getattr(x, attr).description
        ]
        descriptions[name] = {"있음": len(lengths), "사분위": _quartiles(lengths)}

    by_category = {x.isbn for x in books if x.yes24 and is_children_category(x.yes24.category)}
    by_code = {x.isbn for x in books if x.d4l and is_children_addition_code(x.d4l.addition_symbol)}
    return {
        "책": len(books),
        "찾은 출처": dict(found),
        "서명 일치": titles,
        "지은이": writers,
        "소개": descriptions,
        "KDC 있음": sum(1 for x in books if x.d4l and x.d4l.kdc),
        "부가기호 있음": sum(1 for x in books if x.d4l and x.d4l.addition_symbol),
        "어린이": {
            "YES24 분류": len(by_category),
            "부가기호": len(by_code),
            "둘 중 하나": len(by_category | by_code),
            "둘 다": len(by_category & by_code),
            "분류만": len(by_category - by_code),
            "부가기호만": len(by_code - by_category),
        },
    }


def main() -> int:
    if not YES24_FILE.exists() or not SOURCES_FILE.exists():
        print("YES24 원본 파일과 새 출처 파일이 모두 있어야 합니다.", file=sys.stderr)
        return 1
    print(json.dumps(summarize(load_books()), ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
