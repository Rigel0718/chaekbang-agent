"""응답 상품을 Yes24Item으로 바꾼다. 필드마다 관대하게 읽어 한 필드가 어긋나도 나머지는 쓴다."""

import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from app.central.external.yes24.definitions import ITEM_FIELDS, SERIES_NAME_KEY

MAX_PRICE = 2**31 - 1  # 정가 열(Integer)의 상한


@dataclass(frozen=True)
class Yes24Item:
    isbn13: str | None
    title: str | None
    author: str | None
    publisher: str | None
    published_date: date | None
    list_price: int | None
    description: str | None
    table_of_contents: str | None
    cover_url: str | None
    subtitle: str | None
    series_name: str | None
    url: str | None
    category: str | None


def _raw(item: dict[str, Any], name: str) -> Any:
    value: Any = item
    for key in ITEM_FIELDS[name].path:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _fit(name: str, value: str | None) -> str | None:
    """저장 길이를 넘는 값은 비운다."""
    limit = ITEM_FIELDS[name].max_length
    return None if value is not None and limit is not None and len(value) > limit else value


def _clean(value: Any) -> str | None:
    """빈 문자열은 값 없음이다. 줄바꿈은 \\n으로 통일한다."""
    if not isinstance(value, str):
        return None
    return value.replace("\r\n", "\n").replace("\r", "\n").strip() or None


def _text(item: dict[str, Any], name: str) -> str | None:
    return _fit(name, _clean(_raw(item, name)))


def parse_date(value: Any) -> date | None:
    """YYYYMMDD와 YYYY-MM-DD를 읽는다. 문서와 실제 응답의 형식이 달라 둘 다 받는다."""
    text = _clean(value)
    if text is None or not re.fullmatch(r"\d{8}|\d{4}-\d{2}-\d{2}", text):
        return None
    try:
        return datetime.strptime(text.replace("-", ""), "%Y%m%d").date()
    except ValueError:
        return None


def parse_price(value: Any) -> int | None:
    """decimal로 오는 정가를 원 단위 정수로 바꾼다. float를 거치지 않는다."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        price = Decimal(str(value))
    except InvalidOperation:
        return None
    if not price.is_finite() or price != price.to_integral_value() or not 0 <= price <= MAX_PRICE:
        return None
    return int(price)


def _series_name(item: dict[str, Any]) -> str | None:
    series = _raw(item, "series")
    if not isinstance(series, list):
        return None
    names = [_clean(s.get(SERIES_NAME_KEY)) for s in series if isinstance(s, dict)]
    return _fit("series", ", ".join(n for n in names if n) or None)


def parse_item(item: dict[str, Any]) -> Yes24Item:
    return Yes24Item(
        isbn13=_text(item, "isbn13"),
        title=_text(item, "title"),
        author=_text(item, "author"),
        publisher=_text(item, "publisher"),
        published_date=parse_date(_raw(item, "published_date")),
        list_price=parse_price(_raw(item, "list_price")),
        description=_text(item, "introduction") or _text(item, "summary"),
        table_of_contents=_text(item, "table_of_contents"),
        cover_url=_text(item, "cover_url"),
        subtitle=_text(item, "subtitle"),
        series_name=_series_name(item),
        url=_text(item, "url"),
        category=_text(item, "category"),
    )
