"""정보나루 응답 해석: 도서 상세는 Data4LibraryRecord로, 대출 신호는 ISBN 순위로 관대하게 읽는다."""

import html
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.central.external.data4library.definitions import (
    ADDITION_SYMBOL_LENGTH,
    BOOK_FIELDS,
    CO_LOANS_KEY,
    LIST_ISBN_KEY,
    MANIA_KEY,
    POPULAR_DOC_KEY,
    POPULAR_DOCS_KEY,
    POPULAR_LOAN_COUNT_KEY,
    READER_KEY,
    SUBTITLE_MAX_LENGTH,
    TITLE_MAX_LENGTH,
    USAGE_BOOK_KEY,
    USAGE_LOAN_COUNT_KEY,
)
from app.central.external.values import clean, fit, parse_date
from app.core.isbn import InvalidIsbnError, isbn10_to_13, normalize_isbn
from app.core.text import kdc_key


@dataclass(frozen=True)
class Data4LibraryRecord:
    isbn13: str | None
    title: str | None  # 정리한 서명(`split_title`, 숫자 권을 붙인다)
    subtitle: str | None
    author: str | None  # 원문 그대로(`지은이: A ;옮긴이: B`)
    publisher: str | None
    published_date: date | None  # 날짜까지 있을 때만. 해만 오면 None
    kdc: str | None
    category: str | None  # 분류명 원문(`문학 > 한국문학 > 소설`)
    addition_symbol: str | None  # 5자리 숫자일 때만
    volume: str | None
    description: str | None


# 서명 뒤에 붙는 표시. ` :`·` - ` 뒤는 부제, ` =`·` /` 뒤는 대등 서명이다(도서관 목록의 꼴)
_TITLE_PARTS = re.compile(r" (:|=|/|-(?= ))")
_PARALLEL = re.compile(r" [=/]")
_LEADING_QUALIFIER = re.compile(r"^\(([^()]+)\)\s*")  # 괄호 관제: `(어린이) 훈민정음`
_NUMBER = re.compile(r"\d+")


def split_title(bookname: str | None, volume: str | None = None) -> tuple[str | None, str | None]:
    """정보나루 서명을 (서명, 부제)로 정리한다(스펙 "정보나루 서명 정리").

    - 첫 ` :`·` =`·` /`·` - ` 앞이 서명이다. ` :`·` - ` 뒤는 부제이고, 부제 안의 대등 서명은 버린다.
      앞에 공백이 없는 `:`에서는 나누지 않는다.
    - 서명 앞의 괄호 관제는 괄호만 푼다.
    - 권이 숫자뿐이면 서명 뒤에 붙인다. 같은 시리즈의 다른 권이 같은 서명이 되지 않게 한다.
    """
    if bookname is None:
        return None, None
    match = _TITLE_PARTS.search(bookname)
    title, subtitle = bookname, None
    if match is not None:
        title = bookname[: match.start()]
        if match.group(1) in (":", "-"):
            rest = bookname[match.end() :]
            subtitle = clean(_PARALLEL.split(rest, maxsplit=1)[0])
    title = clean(_LEADING_QUALIFIER.sub(lambda m: f"{m.group(1)} ", title.strip()))
    if title and volume and _NUMBER.fullmatch(volume):
        title = f"{title} {volume}"
    return title, subtitle


def _text(book: dict[str, Any], name: str) -> str | None:
    field = BOOK_FIELDS[name]
    return fit(clean(book.get(field.key)), field.max_length)


def _addition_symbol(book: dict[str, Any]) -> str | None:
    code = _text(book, "addition_symbol")
    if code is None or len(code) != ADDITION_SYMBOL_LENGTH or not code.isascii():
        return None
    return code if code.isdigit() else None


def _description(book: dict[str, Any]) -> str | None:
    text = _text(book, "description")
    return clean(html.unescape(text)) if text else None


def parse_book(book: dict[str, Any]) -> Data4LibraryRecord:
    title, subtitle = split_title(_text(book, "bookname"), _text(book, "volume"))
    return Data4LibraryRecord(
        isbn13=_text(book, "isbn13"),
        title=fit(title, TITLE_MAX_LENGTH),
        subtitle=fit(subtitle, SUBTITLE_MAX_LENGTH),
        author=_text(book, "author"),
        publisher=_text(book, "publisher"),
        published_date=parse_date(book.get(BOOK_FIELDS["published_date"].key)),
        kdc=kdc_key(_text(book, "kdc")),
        category=_text(book, "category"),
        addition_symbol=_addition_symbol(book),
        volume=_text(book, "volume"),
        description=_description(book),
    )


# --- 대출 신호 (`add-loan-signals`) ---


@dataclass(frozen=True)
class UsageAnalysis:
    """도서별 이용 분석에서 읽은 ISBN 순위와 기준 책 대출 수. 다른 값은 읽지 않는다."""

    co_loans: tuple[str, ...]
    mania: tuple[str, ...]
    reader: tuple[str, ...]
    loan_count: int | None


@dataclass(frozen=True)
class PopularLoans:
    """인기대출도서의 순위 순서 ISBN과 대출 수(같은 순서)."""

    isbns: tuple[str, ...]
    loan_counts: tuple[int | None, ...]


def list_isbn(raw: Any) -> str | None:
    """목록 원소의 ISBN을 하이픈 없는 13자리로. 10자리는 13자리로 바꾼다. 정리할 수 없으면 None."""
    text = clean(raw) if isinstance(raw, str) else None
    if text is None:
        return None
    for convert in (normalize_isbn, isbn10_to_13):
        try:
            return convert(text)
        except InvalidIsbnError:
            continue
    return None


def _count(raw: Any) -> int | None:
    if isinstance(raw, int):
        return raw
    text = clean(raw) if isinstance(raw, str) else None
    return int(text) if text and text.isdigit() else None


def _entries(value: Any, item_key: str) -> list[dict[str, Any]]:
    """목록 꼴을 관대하게 푼다: `[{key: {...}}]`, `{key: [...]}`, `{key: {...}}`, `[{...}]`."""
    if isinstance(value, dict):
        value = value.get(item_key, value)
    items = value if isinstance(value, list) else [value]
    entries = []
    for item in items:
        inner = item.get(item_key, item) if isinstance(item, dict) else None
        if isinstance(inner, dict):
            entries.append(inner)
    return entries


def _ranked(entries: list[dict[str, Any]], count_key: str) -> tuple[list[str], list[int | None]]:
    isbns: list[str] = []
    counts: list[int | None] = []
    for entry in entries:
        isbn = list_isbn(entry.get(LIST_ISBN_KEY))
        if isbn is None or isbn in isbns:
            continue  # 정리할 수 없는 ISBN은 버리고, 같은 ISBN은 처음 순위만 둔다
        isbns.append(isbn)
        counts.append(_count(entry.get(count_key)))
    return isbns, counts


def parse_usage(data: dict[str, Any]) -> UsageAnalysis:
    def ranking(key: str) -> tuple[str, ...]:
        return tuple(_ranked(_entries(data.get(key), USAGE_BOOK_KEY), USAGE_LOAN_COUNT_KEY)[0])

    book = data.get(USAGE_BOOK_KEY)
    return UsageAnalysis(
        co_loans=ranking(CO_LOANS_KEY),
        mania=ranking(MANIA_KEY),
        reader=ranking(READER_KEY),
        loan_count=_count(book.get(USAGE_LOAN_COUNT_KEY)) if isinstance(book, dict) else None,
    )


def parse_popular(data: dict[str, Any]) -> PopularLoans:
    isbns, counts = _ranked(
        _entries(data.get(POPULAR_DOCS_KEY), POPULAR_DOC_KEY), POPULAR_LOAN_COUNT_KEY
    )
    return PopularLoans(tuple(isbns), tuple(counts))
