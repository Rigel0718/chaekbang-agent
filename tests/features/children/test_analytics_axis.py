"""[features/children] 어린이 분석 축: 배정, 기본값, 기관 분리."""

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.features.children.analytics import AUDIENCE_AXIS
from app.library.analytics.periods import PeriodPreset
from app.library.analytics.scope import BookFilter
from app.library.services import analytics
from tests.helpers import add_audience
from tests.library.analytics_helpers import TODAY, book, loan, member

AXES = (AUDIENCE_AXIS,)


@pytest.fixture(autouse=True)
def _today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "today", lambda: TODAY)


async def _by_audience(session, library_id) -> dict[str, int]:
    result = await analytics.collection_status(
        session, library_id, group_by="audience", book_filter=BookFilter(), axes=AXES
    )
    return {g.key: g.copies for g in result.groups}


async def test_children_and_general_sum(session: AsyncSession, library_a) -> None:
    """[features/children] 어린이 분석 축 / 어린이와 일반의 합"""
    for _ in range(2):
        child, _ = await book(session, library_a.id)
        await add_audience(session, library_a.id, child["id"])
    saved_general, _ = await book(session, library_a.id)
    await add_audience(session, library_a.id, saved_general["id"], audience="general")
    await book(session, library_a.id)
    await book(session, library_a.id)
    result = await analytics.collection_status(
        session, library_a.id, group_by="audience", book_filter=BookFilter(), axes=AXES
    )
    assert [(g.key, g.label, g.copies) for g in result.groups] == [
        ("children", "어린이", 2),
        ("general", "어린이로 분류되지 않음", 3),
    ]
    assert sum(g.copies for g in result.groups) == result.copies


async def test_other_library_audience(session: AsyncSession, library_a, library_b) -> None:
    """[features/children] 어린이 분석 축 / 다른 기관의 어린이 구분"""
    from tests.helpers import make_isbn

    isbn = make_isbn(8765)
    await book(session, library_a.id, isbn=isbn, official_title="같은 책")
    theirs, _ = await book(session, library_b.id, isbn=isbn)
    await add_audience(session, library_b.id, theirs["id"])
    assert await _by_audience(session, library_a.id) == {"children": 0, "general": 1}
    assert await _by_audience(session, library_b.id) == {"children": 1, "general": 0}


async def test_children_loans(session: AsyncSession, library_a) -> None:
    """[features/children] 어린이 분석 축 / 어린이 대출"""
    child, child_copies = await book(session, library_a.id)
    await add_audience(session, library_a.id, child["id"])
    _, adult_copies = await book(session, library_a.id)
    who = await member(session, library_a.id)
    for day in (2, 5):
        await loan(session, child_copies[0], who, date(2026, 11, day), date(2026, 11, day))
    await loan(session, adult_copies[0], who, date(2026, 11, 3), date(2026, 11, 4))
    result = await analytics.loan_stats(
        session,
        library_a.id,
        period=PeriodPreset.THIS_MONTH,
        month=None,
        group_by="audience",
        book_filter=BookFilter(),
        axes=AXES,
        top_n=10,
    )
    assert {g.key: g.loans for g in result.groups} == {"children": 2, "general": 1}
    assert all(g.copies is None for g in result.groups)
    only = await analytics.collection_status(
        session,
        library_a.id,
        group_by=None,
        book_filter=BookFilter(axes={"audience": "children"}),
        axes=AXES,
    )
    assert only.copies == 1
