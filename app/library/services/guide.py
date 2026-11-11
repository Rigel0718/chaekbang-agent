"""도서관 안내 service: 저장과 조회, 개관 여부 판정, 반납 예정일 계산.

날짜는 코드가 정한다. LLM은 이 결과를 말로 옮기기만 한다. REST(`GET /library/guide`), AI 사서의
`get_library_guide` tool, 자체 대출(`create_loan`)이 같은 함수를 쓴다. 그래서 안내가 말한 반납
예정일과 실제 대출의 반납 예정일이 같다.

개관 여부 순서: 임시 휴관 → 공휴일 휴관 → 정기 휴관(그 요일에 운영 시간 구간이 없음) → 개관.
운영 시간을 하나도 등록하지 않았으면 정기 휴관을 판정하지 않고 `unknown`이다.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import get_settings
from app.core.errors import ConflictError
from app.core.holidays import public_holiday
from app.core.tenancy import get_owned
from app.library.models.guide import (
    DueOnClosedDay,
    GuideEntry,
    LibraryClosure,
    LibraryGuide,
    OpeningHours,
)
from app.library.models.library import Library, LoanMode
from app.library.schemas.guide import (
    ClosureCreate,
    DayHours,
    DaySchedule,
    DayStatus,
    Due,
    EntryRead,
    GuideRead,
    GuideUpdate,
    Span,
    Today,
)

WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")
SCHEDULE_DAYS = 7
MAX_POSTPONE_DAYS = 31  # 이 안에 개관일이 없으면 미루지 않는다
REGULAR_CLOSURE = "정기 휴관"
TEMPORARY_CLOSURE = "임시 휴관"
DEFAULT_CLOSURE_DAYS = 90


def day_label(day: date) -> str:
    """사람이 읽는 날짜 표기. 예: 11월 26일 목요일."""
    return f"{day.month}월 {day.day}일 {WEEKDAYS[day.weekday()]}요일"


@dataclass(frozen=True)
class DayInfo:
    status: DayStatus
    spans: tuple[tuple[time, time], ...] = ()
    reason: str | None = None


@dataclass
class GuideRules:
    """한 기관의 안내 규칙. 판정 함수는 DB를 모르고 이 값만 본다."""

    loan_days: int
    loan_mode: LoanMode = LoanMode.INTERNAL
    guide: LibraryGuide | None = None
    hours: dict[int, list[tuple[time, time]]] = field(default_factory=dict)
    closures: dict[date, str | None] = field(default_factory=dict)  # 불러온 범위의 임시 휴관

    @property
    def due_rule(self) -> DueOnClosedDay:
        return self.guide.due_on_closed_day if self.guide else DueOnClosedDay.NEXT_OPEN_DAY

    @property
    def closed_on_public_holidays(self) -> bool:
        return bool(self.guide and self.guide.closed_on_public_holidays)


def day_status(rules: GuideRules, day: date) -> DayInfo:
    if day in rules.closures:
        reason = rules.closures[day]
        label = f"{TEMPORARY_CLOSURE}: {reason}" if reason else TEMPORARY_CLOSURE
        return DayInfo(DayStatus.CLOSED, reason=label)
    if rules.closed_on_public_holidays and (holiday := public_holiday(day)):
        return DayInfo(DayStatus.CLOSED, reason=f"공휴일({holiday})")
    if not rules.hours:
        return DayInfo(DayStatus.UNKNOWN)
    spans = tuple(rules.hours.get(day.weekday(), ()))
    if not spans:
        return DayInfo(DayStatus.CLOSED, reason=REGULAR_CLOSURE)
    return DayInfo(DayStatus.OPEN, spans)


def due_date(rules: GuideRules, loaned_on: date) -> Due:
    """대출일 + 기본 대출 기간. 휴관이고 규칙이 next_open_day면 다음 개관일(unknown은 휴관 아님)."""
    base = loaned_on + timedelta(days=rules.loan_days)
    due = base
    if rules.due_rule == DueOnClosedDay.NEXT_OPEN_DAY:
        for offset in range(MAX_POSTPONE_DAYS + 1):
            candidate = base + timedelta(days=offset)
            if day_status(rules, candidate).status != DayStatus.CLOSED:
                due = candidate
                break
    moved = base if due != base else None
    return Due(
        due_on=due,
        label=day_label(due),
        moved_from=moved,
        moved_from_label=day_label(moved) if moved else None,
    )


async def load_rules(
    session: AsyncSession, library_id: int, start: date, days: int = SCHEDULE_DAYS
) -> GuideRules:
    """start부터 days일의 판정과 그 기간 대출의 반납 예정일에 필요한 규칙을 읽는다."""
    library = await session.get(Library, library_id)
    assert library is not None  # 토큰으로 정해진 기관이다
    guide = await session.scalar(select(LibraryGuide).where(LibraryGuide.library_id == library_id))
    hours: dict[int, list[tuple[time, time]]] = {}
    for row in await session.scalars(
        select(OpeningHours)
        .where(OpeningHours.library_id == library_id)
        .order_by(OpeningHours.weekday, OpeningHours.opens_at)
    ):
        hours.setdefault(row.weekday, []).append((row.opens_at, row.closes_at))
    end = start + timedelta(days=days + library.default_loan_days + MAX_POSTPONE_DAYS)
    closures = {
        row.closed_on: row.reason
        for row in await session.scalars(
            select(LibraryClosure).where(
                LibraryClosure.library_id == library_id,
                LibraryClosure.closed_on >= start,
                LibraryClosure.closed_on <= end,
            )
        )
    }
    return GuideRules(library.default_loan_days, library.loan_mode, guide, hours, closures)


async def compute_due_date(session: AsyncSession, library_id: int, loaned_on: date) -> Due:
    """그 기관에서 loaned_on에 빌리면 반납 예정일. 자체 대출과 안내가 같이 쓴다."""
    return due_date(await load_rules(session, library_id, loaned_on, days=1), loaned_on)


def _spans(spans: tuple[tuple[time, time], ...] | list[tuple[time, time]]) -> list[Span]:
    return [Span(opens_at=a, closes_at=b) for a, b in spans]


def _schedule(rules: GuideRules, day: date) -> DaySchedule:
    info = day_status(rules, day)
    return DaySchedule(
        date=day,
        label=day_label(day),
        status=info.status,
        spans=_spans(info.spans),
        closed_reason=info.reason,
        due_if_borrowed=due_date(rules, day) if info.status != DayStatus.CLOSED else None,
    )


def _local_now() -> datetime:
    return clock.now().astimezone(ZoneInfo(get_settings().library_timezone))


async def get_guide(session: AsyncSession, library_id: int) -> GuideRead:
    today = clock.today()
    rules = await load_rules(session, library_id, today)
    entries = await session.scalars(
        select(GuideEntry).where(GuideEntry.library_id == library_id).order_by(GuideEntry.position)
    )
    days = [_schedule(rules, today + timedelta(days=i)) for i in range(SCHEDULE_DAYS)]
    now = _local_now().time().replace(second=0, microsecond=0)
    first = days[0]
    open_now = (
        None
        if first.status == DayStatus.UNKNOWN
        else any(s.opens_at <= now < s.closes_at for s in first.spans)
    )
    guide = rules.guide
    return GuideRead(
        registered=guide is not None,
        contact_phone=guide.contact_phone if guide else None,
        loan_limit=guide.loan_limit if guide else None,
        loan_days=rules.loan_days,
        loan_mode=rules.loan_mode,
        due_is_estimate=rules.loan_mode == LoanMode.IMPORTED,
        closed_on_public_holidays=rules.closed_on_public_holidays,
        due_on_closed_day=rules.due_rule,
        weekly_hours=[
            DayHours(weekday=i, weekday_label=WEEKDAYS[i], spans=_spans(rules.hours.get(i, [])))
            for i in range(7)
        ],
        entries=[EntryRead.model_validate(e) for e in entries],
        today=Today(**first.model_dump(), now=now.strftime("%H:%M"), open_now=open_now),
        next_days=days,
    )


async def replace_guide(session: AsyncSession, library_id: int, data: GuideUpdate) -> GuideRead:
    """안내 전체를 한 트랜잭션에서 바꾼다. 운영 시간과 자유 항목은 지우고 다시 넣는다."""
    guide = await session.scalar(
        select(LibraryGuide).where(LibraryGuide.library_id == library_id).with_for_update()
    )
    if guide is None:
        guide = LibraryGuide(library_id=library_id)
        session.add(guide)
    guide.contact_phone = data.contact_phone
    guide.loan_limit = data.loan_limit
    guide.closed_on_public_holidays = data.closed_on_public_holidays
    guide.due_on_closed_day = data.due_on_closed_day
    await session.execute(delete(OpeningHours).where(OpeningHours.library_id == library_id))
    await session.execute(delete(GuideEntry).where(GuideEntry.library_id == library_id))
    session.add_all(
        OpeningHours(
            library_id=library_id, weekday=s.weekday, opens_at=s.opens_at, closes_at=s.closes_at
        )
        for s in data.hours
    )
    session.add_all(
        GuideEntry(library_id=library_id, kind=e.kind, title=e.title, body=e.body, position=i)
        for i, e in enumerate(data.entries)
    )
    await session.commit()
    return await get_guide(session, library_id)


async def list_closures(
    session: AsyncSession, library_id: int, start: date | None = None, end: date | None = None
) -> list[LibraryClosure]:
    start = start or clock.today()
    end = end or start + timedelta(days=DEFAULT_CLOSURE_DAYS)
    rows = await session.scalars(
        select(LibraryClosure)
        .where(
            LibraryClosure.library_id == library_id,
            LibraryClosure.closed_on >= start,
            LibraryClosure.closed_on <= end,
        )
        .order_by(LibraryClosure.closed_on)
    )
    return list(rows)


async def add_closure(
    session: AsyncSession, library_id: int, data: ClosureCreate
) -> LibraryClosure:
    closure = LibraryClosure(library_id=library_id, closed_on=data.closed_on, reason=data.reason)
    session.add(closure)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(f"이미 등록한 휴관일입니다: {data.closed_on}") from exc
    await session.refresh(closure)
    return closure


async def delete_closure(session: AsyncSession, library_id: int, closure_id: int) -> None:
    closure = await get_owned(session, LibraryClosure, library_id, closure_id, label="휴관일")
    await session.delete(closure)
    await session.commit()
