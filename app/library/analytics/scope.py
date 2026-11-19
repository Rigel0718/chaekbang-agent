"""책 범위와 묶기 값. 네 분석이 같은 빌더를 쓴다.

`book_facts`는 기관 도서마다 표시 서명·저자, 등록 시각, 분야, 축 값을 한 행으로 낸다. 분석은 이
행을 사본·대출과 이어 센다. 필터(분야 여러 개, 축 값)는 이 행에 건다. 기관은 늘 `library_id`로
좁히고, 회원과 기증자는 읽지 않는다.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from sqlalchemy import ColumnElement, Subquery, func, literal, select

from app.central.models import Book
from app.library.analytics.axes import AnalysisAxis
from app.library.analytics.fields import Field, field_expression, first_call_number
from app.library.models.catalog import AcquisitionType, HoldingStatus, LibraryBook

FIELD = "field"
STATUS = "status"
ACQUISITION = "acquisition_type"

STATUS_LABELS = {
    HoldingStatus.AVAILABLE: "이용 가능",
    HoldingStatus.ON_LOAN: "대출 중",
    HoldingStatus.LOST: "분실",
    HoldingStatus.DAMAGED: "훼손",
}
ACQUISITION_LABELS = {
    AcquisitionType.PURCHASED: "매입",
    AcquisitionType.DONATED: "기증",
    AcquisitionType.UNKNOWN: "알 수 없음",
}


@dataclass(frozen=True)
class BookFilter:
    fields: tuple[Field, ...] = ()  # 비면 전체, 여러 개면 그중 하나에 속하는 책
    axes: Mapping[str, str] = field(default_factory=dict)  # 축 이름 → 값


def axis_column(name: str) -> str:
    return f"axis_{name}"


def book_facts(library_id: int, axes: Sequence[AnalysisAxis]) -> Subquery:
    calls = first_call_number(library_id)
    columns = [
        LibraryBook.id.label("library_book_id"),
        func.coalesce(Book.title, LibraryBook.title).label("title"),
        func.coalesce(Book.author, LibraryBook.author).label("author"),
        LibraryBook.created_at.label("created_at"),
        field_expression(calls.c.call_number).label(FIELD),
    ]
    query = (
        select()
        .select_from(LibraryBook)
        .outerjoin(Book, Book.id == LibraryBook.book_id)
        .outerjoin(calls, calls.c.library_book_id == LibraryBook.id)
    )
    for axis in axes:
        assigned = axis.assign(library_id).subquery(f"assign_{axis.name}")
        book_id, value = list(assigned.c)
        query = query.outerjoin(assigned, book_id == LibraryBook.id)
        columns.append(func.coalesce(value, literal(axis.default)).label(axis_column(axis.name)))
    return query.add_columns(*columns).where(LibraryBook.library_id == library_id).subquery("facts")


def filter_conditions(facts: Subquery, book_filter: BookFilter) -> list[ColumnElement[bool]]:
    conditions: list[ColumnElement[bool]] = []
    if book_filter.fields:
        conditions.append(facts.c[FIELD].in_([f.value for f in book_filter.fields]))
    for name, value in book_filter.axes.items():
        conditions.append(facts.c[axis_column(name)] == value)
    return conditions


@dataclass(frozen=True)
class Grouping:
    key: str
    column: ColumnElement
    values: tuple[tuple[str, str], ...]  # (값, 표시 이름), 결과 순서


def book_grouping(facts: Subquery, key: str, axes: Sequence[AnalysisAxis]) -> Grouping:
    """책의 성질로 묶기: 분야 또는 축."""
    if key == FIELD:
        return Grouping(key, facts.c[FIELD], tuple((f.value, f.value) for f in Field))
    for axis in axes:
        if axis.name == key:
            values = tuple((v, axis.labels[v]) for v in axis.values)
            return Grouping(key, facts.c[axis_column(key)], values)
    raise ValueError(f"묶을 수 없는 값: {key}")
