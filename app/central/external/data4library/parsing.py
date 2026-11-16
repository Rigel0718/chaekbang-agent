"""정보나루 도서 상세 응답을 Data4LibraryRecord로 바꾼다. 필드마다 관대하게 읽는다."""

import html
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from app.central.external.data4library.definitions import (
    ADDITION_SYMBOL_LENGTH,
    BOOK_FIELDS,
    SUBTITLE_MAX_LENGTH,
    TITLE_MAX_LENGTH,
)
from app.central.external.values import clean, fit, parse_date
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
