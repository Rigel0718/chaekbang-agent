"""카카오 책 검색 문서를 KakaoRecord로 바꾼다. 필드마다 관대하게 읽는다."""

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.central.external.kakao.definitions import (
    AUTHOR_MAX_LENGTH,
    AUTHORS_KEY,
    DOCUMENT_FIELDS,
    ISBN13_LENGTH,
    ISBN_KEY,
    NAME_SEPARATOR,
    TRANSLATOR_LABEL,
    TRANSLATORS_KEY,
    VOLATILE_DOCUMENT_KEYS,
)
from app.central.external.values import clean, fit, parse_date, parse_price


@dataclass(frozen=True)
class KakaoRecord:
    isbn13: str | None
    title: str | None
    author: str | None  # 저자·역자 배열을 정해진 꼴로 이은 원문
    publisher: str | None
    published_date: date | None
    list_price: int | None  # 1 이상일 때만
    description: str | None
    cover_url: str | None
    url: str | None


def isbn13_of(document: dict[str, Any]) -> str | None:
    """ISBN 칸(`ISBN10 ISBN13`)에서 13자리 값을 고른다."""
    value = document.get(ISBN_KEY)
    if not isinstance(value, str):
        return None
    for part in value.split():
        if len(part) == ISBN13_LENGTH and part.isascii() and part.isdigit():
            return part
    return None


def _names(document: dict[str, Any], key: str) -> list[str]:
    values = document.get(key)
    if not isinstance(values, list):
        return []
    return [name for name in (clean(v) for v in values) if name]


def join_authors(authors: list[str], translators: list[str]) -> str | None:
    """저자·역자 배열을 저자 원문 하나로 잇는다(`A, B ;옮긴이: C`).

    기관 파일 해석기(`parse_author_text`)가 다시 읽을 수 있는 꼴이라, 공식 서지의 저자 원문에서
    기여자를 다시 만들 수 있다. 저자가 없으면 None이다(역자만으로는 원문을 만들지 않는다).
    """
    if not authors:
        return None
    text = NAME_SEPARATOR.join(authors)
    if translators:
        text += TRANSLATOR_LABEL + NAME_SEPARATOR.join(translators)
    return text


def strip_volatile(document: dict[str, Any]) -> dict[str, Any]:
    """원본 파일에 남길 문서. 변동 값을 뺀다."""
    return {key: value for key, value in document.items() if key not in VOLATILE_DOCUMENT_KEYS}


def _text(document: dict[str, Any], name: str) -> str | None:
    field = DOCUMENT_FIELDS[name]
    return fit(clean(document.get(field.key)), field.max_length)


def parse_document(document: dict[str, Any]) -> KakaoRecord:
    price = parse_price(document.get(DOCUMENT_FIELDS["list_price"].key))
    return KakaoRecord(
        isbn13=isbn13_of(document),
        title=_text(document, "title"),
        author=fit(
            join_authors(_names(document, AUTHORS_KEY), _names(document, TRANSLATORS_KEY)),
            AUTHOR_MAX_LENGTH,
        ),
        publisher=_text(document, "publisher"),
        published_date=parse_date(document.get(DOCUMENT_FIELDS["published_date"].key)),
        list_price=price if price else None,
        description=_text(document, "description"),
        cover_url=_text(document, "cover_url"),
        url=_text(document, "url"),
    )
