"""분석의 분야: KDC 주류 10개와 분류 없음.

책 하나의 분야는 공식 서지 KDC → 기관 도서 KDC → 사본 청구기호 앞 세 자리 숫자 순서로 처음 읽을 수
있는 값의 첫 자리다. 청구기호는 제적이 아닌 사본 중 id가 가장 작은 것을 쓰고, 제적 사본만 있으면
제적 사본 중 가장 작은 것을 쓴다. 별치기호가 앞에 붙은 값(`아 813`)은 읽지 않는다
(`app/core/kdc.py`와 같은 규칙). 키워드·벡터 검색으로 분야를 정하지 않는다. 같은 질문에 같은
숫자가 나와야 한다.
"""

from enum import StrEnum

from sqlalchemy import ColumnElement, String, case, cast, func, literal, select

from app.central.models import Book
from app.core.kdc import KDC_MAIN_CLASSES
from app.library.models.catalog import Holding, HoldingStatus, LibraryBook


class Field(StrEnum):
    """KDC 주류 이름과 분류 없음."""  # 값이 곧 보이는 이름이고, tool 스키마의 설명이 된다

    GENERALITIES = KDC_MAIN_CLASSES[0]  # 총류
    PHILOSOPHY = KDC_MAIN_CLASSES[1]
    RELIGION = KDC_MAIN_CLASSES[2]
    SOCIAL_SCIENCES = KDC_MAIN_CLASSES[3]
    NATURAL_SCIENCES = KDC_MAIN_CLASSES[4]
    TECHNOLOGY = KDC_MAIN_CLASSES[5]
    ARTS = KDC_MAIN_CLASSES[6]
    LANGUAGE = KDC_MAIN_CLASSES[7]
    LITERATURE = KDC_MAIN_CLASSES[8]
    HISTORY = KDC_MAIN_CLASSES[9]
    UNCLASSIFIED = "분류 없음"


MAIN_CLASS_FIELDS = tuple(Field)[:10]

# `app/core/kdc.py`의 `_LEADING_CLASS`와 같은 뜻: 앞 공백 뒤 숫자 세 자리, 그다음은 숫자가 아님
_READABLE = r"^\s*[0-9]{3}([^0-9]|$)"


def _first_digit(value: ColumnElement) -> ColumnElement:
    return func.substr(func.ltrim(value), 1, 1)


def _readable(value: ColumnElement) -> ColumnElement:
    return value.op("~")(_READABLE)


def first_call_number(library_id: int):
    """기관 도서마다 분야에 쓸 사본 청구기호 하나(제적이 아닌 것 먼저, 그다음 작은 id)."""
    ranked = (
        select(
            Holding.library_book_id,
            Holding.call_number,
            func.row_number()
            .over(
                partition_by=Holding.library_book_id,
                order_by=(
                    case((Holding.status == HoldingStatus.WITHDRAWN, 1), else_=0),
                    Holding.id,
                ),
            )
            .label("rank"),
        )
        .where(Holding.library_id == library_id)
        .subquery()
    )
    return (
        select(ranked.c.library_book_id, ranked.c.call_number)
        .where(ranked.c.rank == 1)
        .subquery("first_call_number")
    )


def field_expression(call_number: ColumnElement) -> ColumnElement:
    """분야 이름 식. `Book`·`LibraryBook`과 청구기호 열이 FROM에 있어야 한다."""
    digit = case(
        (_readable(Book.kdc), _first_digit(Book.kdc)),
        (_readable(LibraryBook.kdc), _first_digit(LibraryBook.kdc)),
        (_readable(call_number), _first_digit(call_number)),
        else_=None,
    )
    names = case(
        *((digit == str(i), literal(name)) for i, name in enumerate(KDC_MAIN_CLASSES)),
        else_=literal(Field.UNCLASSIFIED.value),
    )
    return cast(names, String)
