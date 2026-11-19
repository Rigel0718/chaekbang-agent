"""[library/collection-analytics] 분석 service: 분야, 기간, 장서, 목록, 대출, 안 빌린 책, 축."""

from datetime import UTC, date, datetime

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.errors import InvalidRequestError
from app.library.analytics.fields import Field
from app.library.analytics.periods import PeriodError, PeriodPreset, resolve_period
from app.library.analytics.scope import BookFilter
from app.library.models.catalog import HoldingStatus
from app.library.services import analytics
from tests.library.analytics_helpers import TODAY, book, kind_axis, loan, member

NONE = BookFilter()


@pytest.fixture(autouse=True)
def _today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "today", lambda: TODAY)


async def _status(session, library_id, group_by=None, book_filter=NONE, axes=()):
    return await analytics.collection_status(
        session, library_id, group_by=group_by, book_filter=book_filter, axes=axes
    )


def _groups(result) -> dict[str, int]:
    return {g.key: g.copies for g in result.groups}


async def _stats(
    session,
    library_id,
    *,
    group_by=None,
    period=PeriodPreset.THIS_MONTH,
    month=None,
    book_filter=NONE,
    axes=(),
    top_n=10,
):
    return await analytics.loan_stats(
        session,
        library_id,
        period=period if month is None else None,
        month=month,
        group_by=group_by,
        book_filter=book_filter,
        axes=axes,
        top_n=top_n,
    )


# 분야 결정


async def test_field_official_first(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 분야 결정 / 공식 서지 KDC가 먼저"""
    await book(session, library_a.id, official_kdc="813.7", kdc="400")
    result = await _status(session, library_a.id, "field")
    assert _groups(result)[Field.LITERATURE] == 1
    assert _groups(result)[Field.NATURAL_SCIENCES] == 0


async def test_field_from_call_number(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 분야 결정 / 청구기호로 채움"""
    await book(session, library_a.id, call_number="473.1-김12ㄱ")
    assert _groups(await _status(session, library_a.id, "field"))[Field.NATURAL_SCIENCES] == 1


async def test_field_prefixed_call_number(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 분야 결정 / 별치기호 청구기호"""
    await book(session, library_a.id, call_number="아 813-김12ㄱ")
    groups = _groups(await _status(session, library_a.id, "field"))
    assert groups[Field.UNCLASSIFIED] == 1
    assert groups[Field.LITERATURE] == 0


async def test_field_unclassified_group(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 분야 결정 / 분류 없음도 그룹"""
    await book(session, library_a.id, kdc="813.7")
    await book(session, library_a.id, "available", "lost")
    result = await _status(session, library_a.id, "field")
    assert [g.key for g in result.groups] == [f.value for f in Field]
    assert _groups(result)[Field.UNCLASSIFIED] == 2
    assert sum(g.copies for g in result.groups) == result.copies == 3


# 공통 필터


async def test_filter_many_fields(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 공통 필터 / 분야 여러 개"""
    await book(session, library_a.id, "available", "available", kdc="400")
    await book(session, library_a.id, kdc="512")
    await book(session, library_a.id, kdc="813")
    both = BookFilter(fields=(Field.NATURAL_SCIENCES, Field.TECHNOLOGY))
    assert (await _status(session, library_a.id, book_filter=both)).copies == 3


async def test_filter_with_grouping(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 공통 필터 / 필터와 묶기"""
    await book(session, library_a.id, "available", "lost", kdc="400")
    await book(session, library_a.id, "damaged", kdc="813")
    science = BookFilter(fields=(Field.NATURAL_SCIENCES,))
    groups = _groups(await _status(session, library_a.id, "status", science))
    assert groups == {"available": 1, "on_loan": 0, "lost": 1, "damaged": 0}


def test_filter_unknown_field() -> None:
    """[library/collection-analytics] 공통 필터 / 없는 분야 값"""
    with pytest.raises(ValueError):
        Field("과학")


# 장서 현황


async def _withdrawn_fixture(session, library_id):
    await book(session, library_id, "available", "lost", "damaged", "withdrawn")
    await book(session, library_id, "withdrawn")


async def test_status_withdrawn_and_lost(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 장서 현황 / 제적과 분실"""
    await _withdrawn_fixture(session, library_a.id)
    result = await _status(session, library_a.id)
    assert (result.copies, result.titles, result.withdrawn_copies) == (3, 1, 2)
    assert result.groups == []


async def test_status_grouped_by_status(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 장서 현황 / 상태로 묶기"""
    await _withdrawn_fixture(session, library_a.id)
    groups = _groups(await _status(session, library_a.id, "status"))
    assert groups == {"available": 1, "on_loan": 0, "lost": 1, "damaged": 1}


async def test_status_group_sums(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 장서 현황 / 그룹 합"""
    await _withdrawn_fixture(session, library_a.id)
    await book(session, library_a.id, kdc="400", acquisition="donated", donor="이웃")
    axis = kind_axis({})
    total = await _status(session, library_a.id)
    for key in ("field", "status", "acquisition_type", "kind"):
        result = await _status(session, library_a.id, key, axes=(axis,))
        assert sum(g.copies for g in result.groups) == total.copies == 4, key
        assert result.titles == total.titles == 2, key


async def test_status_acquisition(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 장서 현황 / 입수 구분으로 묶기"""
    await book(session, library_a.id, "available", "available")
    await book(session, library_a.id, acquisition="donated", donor="이웃")
    await book(session, library_a.id, acquisition="unknown")
    groups = _groups(await _status(session, library_a.id, "acquisition_type"))
    assert groups == {"purchased": 2, "donated": 1, "unknown": 1}


# 상태별 사본 목록과 표시 값


async def test_list_lost(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 상태별 사본 목록 / 분실 사본"""
    await book(session, library_a.id, "lost", "lost", "available", call_number="813-가")
    result = await analytics.holdings_by_status(
        session, library_a.id, status=HoldingStatus.LOST, book_filter=NONE, limit=20
    )
    assert result.total == result.shown == 2
    assert {item.status for item in result.items} == {HoldingStatus.LOST}
    assert result.items[0].call_number == "813-가"


async def test_list_withdrawn_rejected(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 상태별 사본 목록 / 제적 선택"""
    with pytest.raises(InvalidRequestError):
        await analytics.holdings_by_status(
            session, library_a.id, status=HoldingStatus.WITHDRAWN, book_filter=NONE, limit=20
        )


async def test_list_synced_at_for_external(session: AsyncSession, library_b) -> None:
    """[library/collection-analytics] 상태별 사본 목록 / 분실 사본 (외부 대출 기관의 갱신 시각)"""
    _, holdings = await book(session, library_b.id, "on_loan")
    synced = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)
    await session.execute(
        text("UPDATE holdings SET last_synced_at = :t WHERE id = :id"),
        {"t": synced, "id": holdings[0]["id"]},
    )
    result = await analytics.holdings_by_status(
        session, library_b.id, status=HoldingStatus.ON_LOAN, book_filter=NONE, limit=20
    )
    assert result.items[0].last_synced_at == synced


async def test_display_title(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 표시 값 / 공식 서지 서명"""
    await book(session, library_a.id, "lost", title="기관 서명 가", official_title="공식 서명 나")
    await book(session, library_a.id, "lost", title="기관 서명 다")
    result = await analytics.holdings_by_status(
        session, library_a.id, status=HoldingStatus.LOST, book_filter=NONE, limit=20
    )
    assert [item.title for item in result.items] == ["공식 서명 나", "기관 서명 다"]


# 기간


def test_period_presets() -> None:
    """[library/collection-analytics] 기간 / 프리셋 계산"""
    expected = {
        PeriodPreset.THIS_MONTH: (date(2026, 11, 1), date(2026, 11, 19)),
        PeriodPreset.LAST_MONTH: (date(2026, 10, 1), date(2026, 10, 31)),
        PeriodPreset.LAST_30_DAYS: (date(2026, 10, 21), date(2026, 11, 19)),
        PeriodPreset.LAST_90_DAYS: (date(2026, 8, 22), date(2026, 11, 19)),
        PeriodPreset.THIS_YEAR: (date(2026, 1, 1), date(2026, 11, 19)),
        PeriodPreset.LAST_YEAR: (date(2025, 1, 1), date(2025, 12, 31)),
        PeriodPreset.LAST_365_DAYS: (date(2025, 11, 20), date(2026, 11, 19)),
    }
    for preset, (start, end) in expected.items():
        period = resolve_period(preset, None, TODAY)
        assert (period.start, period.end) == (start, end), preset
    assert resolve_period(PeriodPreset.THIS_MONTH, None, TODAY).label == "2026년 11월 1일~19일"


def test_period_past_month() -> None:
    """[library/collection-analytics] 기간 / 지나지 않은 달"""
    period = resolve_period(None, 12, TODAY)
    assert (period.start, period.end, period.in_progress) == (
        date(2025, 12, 1),
        date(2025, 12, 31),
        False,
    )


def test_period_this_month_number() -> None:
    """[library/collection-analytics] 기간 / 이번 달 숫자"""
    period = resolve_period(None, 11, TODAY)
    assert (period.start, period.end, period.in_progress) == (
        date(2026, 11, 1),
        date(2026, 11, 19),
        True,
    )


def test_period_needs_exactly_one() -> None:
    """[library/collection-analytics] 기간 / 둘 다 또는 둘 다 없음"""
    with pytest.raises(PeriodError):
        resolve_period(PeriodPreset.THIS_MONTH, 11, TODAY)
    with pytest.raises(PeriodError):
        resolve_period(None, None, TODAY)
    with pytest.raises(PeriodError):
        resolve_period(None, 13, TODAY)


# 대출 통계


async def test_loans_period_bounds(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 대출 통계 / 기간 경계"""
    _, holdings = await book(session, library_a.id, *["available"] * 4)
    who = await member(session, library_a.id)
    days = [date(2026, 10, 1), date(2026, 10, 31), date(2026, 9, 30), date(2026, 11, 1)]
    for holding, day in zip(holdings, days, strict=True):
        await loan(session, holding, who, day, returned_on=day)
    assert (await _stats(session, library_a.id, period=PeriodPreset.LAST_MONTH)).loans == 2


async def test_loans_of_withdrawn_copy(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 대출 통계 / 제적 사본의 대출"""
    _, holdings = await book(session, library_a.id, "available")
    who = await member(session, library_a.id)
    await loan(session, holdings[0], who, date(2026, 11, 2), returned_on=date(2026, 11, 5))
    await session.execute(
        text("UPDATE holdings SET status = 'withdrawn' WHERE id = :id"), {"id": holdings[0]["id"]}
    )
    assert (await _stats(session, library_a.id)).loans == 1


async def test_loans_current_and_overdue(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 대출 통계 / 지금 대출 중과 연체"""
    _, holdings = await book(session, library_a.id, *["available"] * 3)
    who = await member(session, library_a.id)
    await loan(session, holdings[0], who, date(2026, 11, 4), due_on=date(2026, 11, 18))
    await loan(session, holdings[1], who, date(2026, 11, 10))
    await loan(session, holdings[2], who, date(2026, 11, 12))
    for period in (PeriodPreset.THIS_MONTH, PeriodPreset.LAST_YEAR):
        current = (await _stats(session, library_a.id, period=period)).current
        assert (current.on_loan, current.overdue) == (3, 1)


async def test_loans_per_copy(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 분야별 권당 대출 / 권당 대출"""
    _, holdings = await book(session, library_a.id, *["available"] * 4, kdc="400")
    who = await member(session, library_a.id)
    for i in range(6):
        day = date(2026, 11, 1 + i)
        await loan(session, holdings[i % 4], who, day, returned_on=day)
    result = await _stats(session, library_a.id, group_by="field")
    science = next(g for g in result.groups if g.key == Field.NATURAL_SCIENCES)
    assert (science.copies, science.loans, science.loans_per_copy) == (4, 6, 1.5)
    literature = next(g for g in result.groups if g.key == Field.LITERATURE)
    assert (literature.copies, literature.loans, literature.loans_per_copy) == (0, 0, None)


async def test_loans_per_copy_all_withdrawn(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 분야별 권당 대출 / 사본 없는 분야"""
    _, holdings = await book(session, library_a.id, "available", kdc="813")
    who = await member(session, library_a.id)
    await loan(session, holdings[0], who, date(2026, 11, 2), returned_on=date(2026, 11, 3))
    await session.execute(
        text("UPDATE holdings SET status = 'withdrawn' WHERE id = :id"), {"id": holdings[0]["id"]}
    )
    result = await _stats(session, library_a.id, group_by="field")
    literature = next(g for g in result.groups if g.key == Field.LITERATURE)
    assert (literature.copies, literature.loans, literature.loans_per_copy) == (0, 1, None)


# 책 순위


async def _loans_for(session, holding, who, n: int, start_day: int = 1):
    for i in range(n):
        day = date(2026, 11, start_day + i)
        await loan(session, holding, who, day, returned_on=day)


async def test_ranking_tie_order(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 책 순위 / 같은 수의 순서"""
    who = await member(session, library_a.id)
    _, top = await book(session, library_a.id, title="가장 많이")
    _, b = await book(session, library_a.id, title="나무")
    _, c = await book(session, library_a.id, title="다람쥐")
    await _loans_for(session, top[0], who, 3)
    await _loans_for(session, c[0], who, 2)
    await _loans_for(session, b[0], who, 2, start_day=5)
    first = await _stats(session, library_a.id, group_by="book", top_n=2)
    second = await _stats(session, library_a.id, group_by="book", top_n=2)
    assert [i.title for i in first.ranking.items] == ["가장 많이", "나무"]
    assert first.ranking == second.ranking
    assert (first.ranking.total, first.ranking.shown, first.ranking.truncated) == (3, 2, True)


async def test_ranking_top_n_limit(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 책 순위 / 상한 초과"""
    with pytest.raises(InvalidRequestError):
        await _stats(session, library_a.id, group_by="book", top_n=21)


async def test_ranking_withdrawn_book(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 책 순위 / 제적된 인기 책"""
    who = await member(session, library_a.id)
    _, holdings = await book(session, library_a.id, title="인기 책")
    await _loans_for(session, holdings[0], who, 3)
    await session.execute(
        text("UPDATE holdings SET status = 'withdrawn' WHERE id = :id"), {"id": holdings[0]["id"]}
    )
    _, kept = await book(session, library_a.id, title="남은 책")
    await _loans_for(session, kept[0], who, 1, start_day=10)
    ranking = (await _stats(session, library_a.id, group_by="book")).ranking
    assert [(i.title, i.in_collection) for i in ranking.items] == [
        ("인기 책", False),
        ("남은 책", True),
    ]


# 안 빌린 책


async def _unborrowed(session, library_id, *, limit=20, period=PeriodPreset.LAST_365_DAYS, **kw):
    return await analytics.unborrowed_books(
        session, library_id, period=period, month=None, book_filter=NONE, limit=limit, **kw
    )


async def test_unborrowed_registered_in_period(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 안 빌린 책 / 기간 중 등록"""
    await book(session, library_a.id, title="오래된 책")
    await book(session, library_a.id, title="새 책", created_at=datetime(2026, 11, 3, tzinfo=UTC))
    result = await _unborrowed(session, library_a.id, period=PeriodPreset.THIS_MONTH)
    assert [i.title for i in result.items] == ["오래된 책"]


async def test_unborrowed_one_copy_borrowed(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 안 빌린 책 / 한 사본이라도 빌림"""
    _, holdings = await book(session, library_a.id, "available", "available", title="반쯤")
    who = await member(session, library_a.id)
    await loan(session, holdings[1], who, date(2026, 6, 1), returned_on=date(2026, 6, 10))
    await book(session, library_a.id, title="아무도")
    result = await _unborrowed(session, library_a.id)
    assert [i.title for i in result.items] == ["아무도"]


async def test_unborrowed_withdrawn_only(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 안 빌린 책 / 제적만 남은 서명"""
    await book(session, library_a.id, "withdrawn", "withdrawn", title="없는 책")
    assert (await _unborrowed(session, library_a.id)).total == 0


# 목록 한도와 잘림


async def test_unborrowed_truncated(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 목록 한도와 잘림 / 잘린 목록"""
    for i in range(25):
        await book(session, library_a.id, title=f"안 빌린 {i:02d}")
    result = await _unborrowed(session, library_a.id, limit=20)
    assert (result.total, result.shown, result.truncated) == (25, 20, True)
    assert result.items[0].title == "안 빌린 00"


async def test_list_limit_over_max(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 목록 한도와 잘림 / 목록 상한 초과"""
    with pytest.raises(InvalidRequestError):
        await _unborrowed(session, library_a.id, limit=51)
    with pytest.raises(InvalidRequestError):
        await analytics.holdings_by_status(
            session, library_a.id, status=HoldingStatus.LOST, book_filter=NONE, limit=51
        )


# 분석 축


async def test_axis_unassigned_is_default(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 분석 축 / 배정 없는 책"""
    first, _ = await book(session, library_a.id)
    await book(session, library_a.id)
    await book(session, library_a.id, "available", "lost")
    axis = kind_axis({first["id"]: "a"})
    result = await _status(session, library_a.id, "kind", axes=(axis,))
    assert [(g.key, g.label, g.copies) for g in result.groups] == [("a", "가", 1), ("b", "나", 3)]
    only_a = await _status(
        session, library_a.id, book_filter=BookFilter(axes={"kind": "a"}), axes=(axis,)
    )
    assert only_a.copies == 1


async def test_axis_unknown_value(session: AsyncSession, library_a) -> None:
    """[library/collection-analytics] 분석 축 / 배정 없는 책 (모르는 축 값은 거절)"""
    with pytest.raises(InvalidRequestError):
        await _status(
            session, library_a.id, book_filter=BookFilter(axes={"kind": "c"}), axes=(kind_axis({}),)
        )
    with pytest.raises(InvalidRequestError):
        await _status(session, library_a.id, "kind")


# 기관 분리


async def _everything(session, library_id, axes=()):
    return (
        [
            await _status(session, library_id, key, axes=axes)
            for key in (None, "field", "status", "acquisition_type", *[a.name for a in axes])
        ]
        + [
            await _stats(
                session, library_id, group_by=key, period=PeriodPreset.LAST_365_DAYS, axes=axes
            )
            for key in (None, "field", "book", *[a.name for a in axes])
        ]
        + [
            await analytics.holdings_by_status(
                session, library_id, status=status, book_filter=NONE, axes=axes, limit=50
            )
            for status in analytics.LISTABLE_STATUSES
        ]
        + [await _unborrowed(session, library_id, axes=axes)]
    )


async def test_other_library_same_book(session: AsyncSession, library_a, library_b) -> None:
    """[library/collection-analytics] 분석의 기관 범위 / 다른 기관의 같은 책"""
    from tests.helpers import make_isbn

    isbn = make_isbn(4321)
    _, mine = await book(session, library_a.id, "available", "lost", isbn=isbn, official_kdc="400")
    who = await member(session, library_a.id)
    await loan(session, mine[0], who, date(2026, 11, 2), returned_on=date(2026, 11, 4))
    before = await _everything(session, library_a.id)

    from tests.helpers import add_holding, add_library_book

    other = await add_library_book(session, library_b.id, isbn, kdc="813")
    holdings = [
        await add_holding(session, library_b.id, other["id"], f"B{i}", status=s)
        for i, s in enumerate(("available", "lost", "damaged", "withdrawn"))
    ]
    them = await member(session, library_b.id)
    await loan(session, holdings[0], them, date(2026, 11, 3))
    await book(session, library_b.id, "available", kdc="400")
    after = await _everything(session, library_a.id)
    assert [r.model_dump(exclude={"items"}) for r in after] == [
        r.model_dump(exclude={"items"}) for r in before
    ]
