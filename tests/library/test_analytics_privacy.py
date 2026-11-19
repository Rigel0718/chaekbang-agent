"""[library/collection-analytics] 분석 결과의 개인정보: 심은 값과 결과 필드 허용 목록."""

from datetime import date

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.library.analytics.fields import Field
from app.library.analytics.periods import PeriodPreset
from app.library.analytics.scope import BookFilter
from app.library.services import analytics
from tests.library.analytics_helpers import TODAY, book, kind_axis, loan, member

CANARY_NAME = "카나리아회원"
CANARY_NUMBER = "CANARY7788"
CANARY_DONOR = "카나리아기증자"


@pytest.fixture(autouse=True)
def _today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "today", lambda: TODAY)


async def _all_results(session, library_id, axes):
    filters = [
        BookFilter(),
        BookFilter(fields=(Field.NATURAL_SCIENCES, Field.UNCLASSIFIED)),
        BookFilter(axes={"kind": "a"}),
    ]
    results = []
    for book_filter in filters:
        for key in (None, "field", "status", "acquisition_type", "kind"):
            results.append(
                await analytics.collection_status(
                    session, library_id, group_by=key, book_filter=book_filter, axes=axes
                )
            )
        for key in (None, "field", "book", "kind"):
            results.append(
                await analytics.loan_stats(
                    session,
                    library_id,
                    period=PeriodPreset.LAST_365_DAYS,
                    month=None,
                    group_by=key,
                    book_filter=book_filter,
                    axes=axes,
                    top_n=20,
                )
            )
        for status in analytics.LISTABLE_STATUSES:
            results.append(
                await analytics.holdings_by_status(
                    session,
                    library_id,
                    status=status,
                    book_filter=book_filter,
                    axes=axes,
                    limit=50,
                )
            )
        results.append(
            await analytics.unborrowed_books(
                session,
                library_id,
                period=PeriodPreset.THIS_MONTH,
                month=None,
                book_filter=book_filter,
                axes=axes,
                limit=50,
            )
        )
    return results


async def test_planted_values_absent(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 분석 결과의 개인정보 / 심은 값"""
    first, holdings = await book(
        session,
        library_a.id,
        "available",
        "lost",
        "damaged",
        kdc="400",
        acquisition="donated",
        donor=CANARY_DONOR,
    )
    await book(session, library_a.id, "available", donor=CANARY_DONOR, acquisition="donated")
    from tests.helpers import add_member

    who = await add_member(session, library_a.id, CANARY_NUMBER, CANARY_NAME)
    await loan(session, holdings[0], who, date(2026, 11, 1), due_on=date(2026, 11, 10))
    other = await member(session, library_a.id, name=CANARY_NAME)
    await loan(session, holdings[0], other, date(2026, 3, 1), returned_on=date(2026, 3, 9))
    results = await _all_results(session, library_a.id, (kind_axis({first["id"]: "a"}),))
    assert len(results) == 3 * (5 + 4 + 3 + 1)
    for result in results:
        dumped = result.model_dump_json()
        for canary in (CANARY_NAME, CANARY_NUMBER, CANARY_DONOR):
            assert canary not in dumped
