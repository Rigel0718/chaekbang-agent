"""분석 테스트 도우미: 분야·사본·대출을 짧게 만든다. 오늘은 2026-11-19로 고정한다."""

from datetime import UTC, date, datetime
from itertools import count

from sqlalchemy import literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.library.analytics.axes import AnalysisAxis
from tests.helpers import add_book, add_holding, add_library_book, add_loan, add_member, make_isbn

TODAY = date(2026, 11, 19)
OLD = datetime(2025, 1, 1, tzinfo=UTC)  # 모든 기간보다 먼저 등록된 책

_numbers = count(1)


async def book(
    session: AsyncSession,
    library_id: int,
    *statuses: str,
    title: str | None = None,
    kdc: str | None = None,
    official_kdc: str | None = None,
    official_title: str | None = None,
    call_number: str | None = None,
    created_at: datetime = OLD,
    acquisition: str = "purchased",
    donor: str | None = None,
    isbn: str | None = None,
):
    """기관 도서 하나와 상태별 사본(기본 이용 가능 하나). 사본 목록을 함께 돌려준다."""
    n = next(_numbers)
    book_id = None
    if official_kdc is not None or official_title is not None:
        isbn = isbn or make_isbn(n + 3000)
        official = await add_book(
            session, isbn, title=official_title or f"공식 {n}", kdc=official_kdc
        )
        book_id = official["id"]
    library_book = await add_library_book(
        session,
        library_id,
        isbn,
        book_id=book_id,
        title=title or f"책 {n:03d}",
        kdc=kdc,
        created_at=created_at,
    )
    holdings = []
    for status in statuses or ("available",):
        holdings.append(
            await add_holding(
                session,
                library_id,
                library_book["id"],
                f"AN{next(_numbers):05d}",
                status=status,
                call_number=call_number,
                acquisition_type=acquisition,
                purchase_price=None if acquisition != "purchased" else 13500,
                donor=donor,
            )
        )
    return library_book, holdings


async def member(session: AsyncSession, library_id: int, name: str = "김이용"):
    return await add_member(session, library_id, f"M{next(_numbers):05d}", name)


async def loan(
    session, holding, who, loaned_on: date, returned_on: date | None = None, due_on=None
):
    return await add_loan(
        session, holding, who, loaned_on=loaned_on, returned_on=returned_on, due_on=due_on
    )


def kind_axis(assigned: dict[int, str]) -> AnalysisAxis:
    """값 `a`·`b`, 기본값 `b`인 시험용 축. assigned는 기관 도서 id → 값."""

    def assign(library_id: int):
        rows = [
            select(literal(book_id).label("library_book_id"), literal(value).label("value"))
            for book_id, value in assigned.items()
        ]
        if not rows:
            return select(literal(0).label("library_book_id"), literal("a").label("value")).where(
                literal(False)
            )
        query = rows[0]
        for row in rows[1:]:
            query = query.union_all(row)
        return query

    return AnalysisAxis(
        name="kind",
        description="시험용 축",
        values=("a", "b"),
        default="b",
        labels={"a": "가", "b": "나"},
        assign=assign,
    )
