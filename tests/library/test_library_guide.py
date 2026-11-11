"""[library/library-guide] 안내 service: 개관 여부 판정, 반납 예정일 계산, 저장과 기관 분리.

API 시나리오는 tests/library/test_library_guide_api.py에 있다.
"""

from datetime import UTC, date, datetime, time, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.errors import ConflictError, NotFoundError
from app.library.models.guide import DueOnClosedDay, LibraryGuide
from app.library.schemas.guide import ClosureCreate, DayStatus, GuideUpdate
from app.library.services import guide as svc
from tests.conftest import Tenant

WED = date(2026, 11, 11)  # 수요일
NINE, NOON, ONE, SIX = time(9), time(12), time(13), time(18)


def _rules(
    *,
    hours: dict[int, list[tuple[time, time]]] | None = None,
    closures: dict[date, str | None] | None = None,
    holidays: bool = False,
    rule: DueOnClosedDay = DueOnClosedDay.NEXT_OPEN_DAY,
    loan_days: int = 14,
) -> svc.GuideRules:
    guide = LibraryGuide(closed_on_public_holidays=holidays, due_on_closed_day=rule)
    return svc.GuideRules(loan_days, guide=guide, hours=hours or {}, closures=closures or {})


# 화–일 09:00–18:00, 월요일 정기 휴관
WEEK = {d: [(NINE, SIX)] for d in range(1, 7)}


def test_regular_closure() -> None:
    """[library/library-guide] 개관 여부 판정 / 정기 휴관"""
    info = svc.day_status(_rules(hours=WEEK), date(2026, 11, 16))  # 월요일
    assert (info.status, info.reason) == (DayStatus.CLOSED, "정기 휴관")


def test_public_holiday_closure() -> None:
    """[library/library-guide] 개관 여부 판정 / 공휴일 휴관"""
    info = svc.day_status(_rules(hours=WEEK, holidays=True), date(2026, 9, 25))
    assert info.status == DayStatus.CLOSED
    assert "추석" in (info.reason or "")


def test_open_on_public_holiday() -> None:
    """[library/library-guide] 개관 여부 판정 / 공휴일에 여는 기관"""
    info = svc.day_status(_rules(hours=WEEK, holidays=False), date(2026, 9, 25))  # 금요일
    assert info.status == DayStatus.OPEN
    assert info.spans == ((NINE, SIX),)


def test_unknown_without_hours() -> None:
    """[library/library-guide] 개관 여부 판정 / 운영 시간 미등록"""
    assert svc.day_status(_rules(), WED).status == DayStatus.UNKNOWN


def test_temporary_closure_comes_first() -> None:
    info = svc.day_status(_rules(hours=WEEK, closures={WED: "소독"}), WED)
    assert (info.status, info.reason) == (DayStatus.CLOSED, "임시 휴관: 소독")


def test_due_on_open_day() -> None:
    """[library/library-guide] 반납 예정일 계산 / 휴관일이 아닌 반납일"""
    due = svc.due_date(_rules(hours=WEEK), WED)
    assert due.due_on == date(2026, 11, 25)
    assert due.moved_from is None
    assert due.label == "11월 25일 수요일"


def test_due_moves_past_regular_closure() -> None:
    """[library/library-guide] 반납 예정일 계산 / 정기 휴관일로 떨어진 반납일"""
    monday = date(2026, 11, 2)  # 14일 뒤 11-16 월요일
    due = svc.due_date(_rules(hours=WEEK), monday)
    assert due.due_on == date(2026, 11, 17)
    assert due.moved_from == date(2026, 11, 16)
    assert due.moved_from_label == "11월 16일 월요일"


def test_due_kept_on_closed_day() -> None:
    """[library/library-guide] 반납 예정일 계산 / 그대로 두는 기관"""
    due = svc.due_date(_rules(hours=WEEK, rule=DueOnClosedDay.KEEP), date(2026, 11, 2))
    assert due.due_on == date(2026, 11, 16)
    assert due.moved_from is None


def test_due_moves_past_consecutive_closures() -> None:
    """[library/library-guide] 반납 예정일 계산 / 이어지는 휴관

    2026-09-11 + 14일 = 09-25(추석, 공휴일), 09-26(추석 다음날), 09-27은 임시 휴관 → 09-28은 월요일
    정기 휴관 → 09-29 화요일.
    """
    rules = _rules(hours=WEEK, holidays=True, closures={date(2026, 9, 27): None})
    due = svc.due_date(rules, date(2026, 9, 11))
    assert due.due_on == date(2026, 9, 29)
    assert due.moved_from == date(2026, 9, 25)


def test_due_not_moved_when_unknown() -> None:
    """운영 시간을 모르는 날은 휴관으로 보지 않는다. 안내 미등록 기관은 오늘 + 기간이다."""
    assert svc.due_date(_rules(), WED).due_on == date(2026, 11, 25)


def test_due_not_moved_without_open_day() -> None:
    """31일 안에 개관일이 없으면 미루지 않는다."""
    closures = {date(2026, 11, 25) + timedelta(days=i): None for i in range(40)}
    due = svc.due_date(_rules(hours=WEEK, closures=closures), WED)
    assert due.due_on == date(2026, 11, 25)


@pytest.fixture
def fixed_day(monkeypatch: pytest.MonkeyPatch) -> date:
    monkeypatch.setattr(clock, "today", lambda: WED)
    return WED


GUIDE = GuideUpdate(
    contact_phone="031-000-0000",
    loan_limit=5,
    closed_on_public_holidays=True,
    hours=[{"weekday": d, "opens_at": "09:00", "closes_at": "12:00"} for d in range(1, 6)]
    + [{"weekday": d, "opens_at": "13:00", "closes_at": "18:00"} for d in range(1, 6)],
    entries=[
        {"kind": "facility", "title": "화장실", "body": "1층 출입문 오른쪽"},
        {"kind": "rule", "title": "음식물", "body": "열람실에서는 음식을 먹을 수 없어요"},
    ],
)


async def test_empty_guide(session: AsyncSession, library_a: Tenant, fixed_day: date) -> None:
    guide = await svc.get_guide(session, library_a.id)
    assert guide.registered is False
    assert guide.contact_phone is None
    assert guide.entries == []
    assert guide.today.status == DayStatus.UNKNOWN
    assert guide.today.open_now is None
    assert guide.today.due_if_borrowed is not None
    assert guide.today.due_if_borrowed.due_on == date(2026, 11, 25)


async def test_replace_and_schedule(
    session: AsyncSession, library_a: Tenant, fixed_day: date
) -> None:
    await svc.add_closure(session, library_a.id, ClosureCreate(closed_on=date(2026, 11, 25)))
    guide = await svc.replace_guide(session, library_a.id, GUIDE)
    assert guide.registered is True
    assert [e.title for e in guide.entries] == ["화장실", "음식물"]
    assert len(guide.weekly_hours[1].spans) == 2  # 화요일 점심시간
    assert [d.date for d in guide.next_days][0] == WED
    assert len(guide.next_days) == 7
    statuses = {d.label: d.status for d in guide.next_days}
    assert statuses["11월 15일 일요일"] == DayStatus.CLOSED
    assert statuses["11월 16일 월요일"] == DayStatus.CLOSED
    # 14일 뒤 11-25는 임시 휴관 → 11-26 목요일
    assert guide.today.due_if_borrowed is not None
    assert guide.today.due_if_borrowed.label == "11월 26일 목요일"
    assert all(d.due_if_borrowed is None for d in guide.next_days if d.status == DayStatus.CLOSED)


async def test_replace_removes_missing(
    session: AsyncSession, library_a: Tenant, fixed_day: date
) -> None:
    await svc.replace_guide(session, library_a.id, GUIDE)
    guide = await svc.replace_guide(session, library_a.id, GuideUpdate(entries=GUIDE.entries[:1]))
    assert len(guide.entries) == 1
    assert all(not d.spans for d in guide.weekly_hours)
    assert guide.contact_phone is None


async def test_guides_are_separated(
    session: AsyncSession, library_a: Tenant, library_b: Tenant, fixed_day: date
) -> None:
    await svc.replace_guide(session, library_a.id, GUIDE)
    await svc.replace_guide(session, library_b.id, GuideUpdate(contact_phone="02-111-2222"))
    await svc.add_closure(session, library_b.id, ClosureCreate(closed_on=date(2026, 11, 12)))
    a = await svc.get_guide(session, library_a.id)
    b = await svc.get_guide(session, library_b.id)
    assert (a.contact_phone, b.contact_phone) == ("031-000-0000", "02-111-2222")
    assert a.next_days[1].status == DayStatus.OPEN  # B의 임시 휴관은 A에 없다
    assert await svc.list_closures(session, library_a.id) == []
    assert b.due_is_estimate is True and a.due_is_estimate is False


async def test_closure_conflict_and_owner(
    session: AsyncSession, library_a: Tenant, library_b: Tenant, fixed_day: date
) -> None:
    mine = (
        await svc.add_closure(
            session, library_a.id, ClosureCreate(closed_on=date(2026, 11, 20), reason="소독")
        )
    ).id  # 409 뒤 rollback으로 행 객체가 만료되므로 id만 쥔다
    with pytest.raises(ConflictError):
        await svc.add_closure(session, library_a.id, ClosureCreate(closed_on=date(2026, 11, 20)))
    with pytest.raises(NotFoundError):
        await svc.delete_closure(session, library_b.id, mine)
    assert [c.reason for c in await svc.list_closures(session, library_a.id)] == ["소독"]
    await svc.delete_closure(session, library_a.id, mine)
    assert await svc.list_closures(session, library_a.id) == []


async def test_compute_due_date_matches_guide(
    session: AsyncSession, library_a: Tenant, fixed_day: date
) -> None:
    await svc.replace_guide(session, library_a.id, GUIDE)
    await svc.add_closure(session, library_a.id, ClosureCreate(closed_on=date(2026, 11, 25)))
    due = await svc.compute_due_date(session, library_a.id, WED)
    guide = await svc.get_guide(session, library_a.id)
    assert guide.today.due_if_borrowed == due
    assert due.due_on == date(2026, 11, 26)


async def test_open_now(
    session: AsyncSession, library_a: Tenant, fixed_day: date, monkeypatch: pytest.MonkeyPatch
) -> None:
    """지금 열려 있는지는 기관 시간대의 지금 시각과 오늘 구간으로 코드가 정한다. 인증이 clock.now를
    쓰므로 API가 아니라 service로 본다."""
    await svc.replace_guide(session, library_a.id, GUIDE)
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 11, 5, 0, tzinfo=UTC))  # 14:00
    today = (await svc.get_guide(session, library_a.id)).today
    assert (today.now, today.open_now) == ("14:00", True)
    monkeypatch.setattr(clock, "now", lambda: datetime(2026, 11, 11, 3, 30, tzinfo=UTC))  # 12:30
    assert (await svc.get_guide(session, library_a.id)).today.open_now is False
