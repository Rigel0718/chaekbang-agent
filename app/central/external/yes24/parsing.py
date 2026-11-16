"""응답 상품을 Yes24Item으로 바꾼다. 필드마다 관대하게 읽어 한 필드가 어긋나도 나머지는 쓴다."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.central.external.values import clean as _clean
from app.central.external.values import fit, parse_date, parse_price
from app.central.external.yes24.definitions import ITEM_FIELDS, SERIES_NAME_KEY

__all__ = ["Yes24Item", "parse_date", "parse_item", "parse_price"]


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
    series_name: str | None  # 표시용: 시리즈를 ", "로 이은 것
    url: str | None
    category: str | None
    series_names: tuple[str, ...] = ()  # 응답 목록 그대로(빈 값 제외). 시리즈 키는 이것으로 만든다


def _raw(item: dict[str, Any], name: str) -> Any:
    value: Any = item
    for key in ITEM_FIELDS[name].path:
        value = value.get(key) if isinstance(value, dict) else None
    return value


def _fit(name: str, value: str | None) -> str | None:
    """저장 길이를 넘는 값은 비운다."""
    return fit(value, ITEM_FIELDS[name].max_length)


def _text(item: dict[str, Any], name: str) -> str | None:
    return _fit(name, _clean(_raw(item, name)))


def _series_names(item: dict[str, Any]) -> tuple[str, ...]:
    series = _raw(item, "series")
    if not isinstance(series, list):
        return ()
    names = (_clean(s.get(SERIES_NAME_KEY)) for s in series if isinstance(s, dict))
    return tuple(n for n in names if n)


def _series_name(names: tuple[str, ...]) -> str | None:
    return _fit("series", ", ".join(names) or None)


def parse_item(item: dict[str, Any]) -> Yes24Item:
    series_names = _series_names(item)
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
        series_name=_series_name(series_names),
        url=_text(item, "url"),
        category=_text(item, "category"),
        series_names=series_names,
    )
