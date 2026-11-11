"""안내 평가의 고정 값: 가상 평가 안내, 날짜 고정, 시나리오별 안내 넣기·지우기, 판정 기준값.

날짜는 2026-11-11(수) 14:00(기관 시간대)으로 고정한다. 오늘 빌리면 기본 14일 → 11-25(임시 휴관)
→ 11월 26일 목요일로 미뤄진다. 모든 값은 가상이다(연락처 `031-000-0000`).

실행기는 tool 결과 원문을 기록하지 않으므로, 판정(`invented_guide`, `contains`)은 같은 service로
계산한 값(`guide_basis`)을 기준으로 보고 그 값을 결과 파일에 함께 쓴다.
"""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.library.models.catalog import Holding
from app.library.models.guide import GuideEntry, LibraryClosure, LibraryGuide, OpeningHours
from app.library.schemas.guide import ClosureCreate, GuideUpdate
from app.library.services import guide as guide_service
from evals.librarian.catalog import BookState, SampleCatalog
from evals.librarian.scenarios import GUIDE_PHONE, GuideSetup

EVAL_TODAY = date(2026, 11, 11)
EVAL_NOW = datetime(2026, 11, 11, 5, 0, tzinfo=UTC)  # Asia/Seoul 14:00
SHELF = "2층 문학 서가"

_WEEKDAYS = range(1, 5)  # 화–금
EVAL_GUIDE = GuideUpdate(
    contact_phone=GUIDE_PHONE,
    loan_limit=5,
    closed_on_public_holidays=True,
    hours=[
        *({"weekday": d, "opens_at": "09:00", "closes_at": "12:00"} for d in _WEEKDAYS),
        *({"weekday": d, "opens_at": "13:00", "closes_at": "18:00"} for d in _WEEKDAYS),
        {"weekday": 5, "opens_at": "09:00", "closes_at": "13:00"},  # 토요일. 일·월은 정기 휴관
    ],
    entries=[
        {"kind": "facility", "title": "화장실", "body": "1층 출입문 오른쪽에 있어요"},
        {"kind": "facility", "title": "어린이 자료실", "body": "2층 계단 옆"},
        {"kind": "rule", "title": "음식물", "body": "열람실에서는 음식을 먹을 수 없어요"},
    ],
)
EVAL_CLOSURE = ClosureCreate(closed_on=date(2026, 11, 25), reason="소독")


@contextmanager
def fixed_clock() -> Iterator[None]:
    """오늘을 고정하고, 지금은 EVAL_NOW부터 실제로 흐른 만큼 더한다(실행 시간 기록이 남게)."""
    original_today, original_now = clock.today, clock.now
    started = original_now()
    clock.today = lambda: EVAL_TODAY  # type: ignore[assignment]
    clock.now = lambda: EVAL_NOW + (original_now() - started)  # type: ignore[assignment]
    try:
        yield
    finally:
        clock.today, clock.now = original_today, original_now  # type: ignore[assignment]


async def shelve_one(session: AsyncSession, catalog: SampleCatalog) -> int:
    """대출 가능한 책 하나의 사본을 SHELF에 둔다. `{shelved_title}` 시나리오가 쓴다."""
    book_id = catalog.with_state(BookState.AVAILABLE)[0]
    await session.execute(
        update(Holding)
        .where(Holding.library_id == catalog.library_id, Holding.library_book_id == book_id)
        .values(shelf_location=SHELF, call_number="813.7-평가")
    )
    await session.commit()
    catalog.shelved = book_id
    return book_id


async def setup_guide(session: AsyncSession, library_id: int, setup: GuideSetup) -> None:
    """시나리오 전에 안내를 넣거나 지운다. 되돌림 트랜잭션 안이다."""
    for model in (OpeningHours, GuideEntry, LibraryClosure, LibraryGuide):
        await session.execute(delete(model).where(model.library_id == library_id))
    await session.commit()
    if setup == GuideSetup.FULL:
        await guide_service.replace_guide(session, library_id, EVAL_GUIDE)
        await guide_service.add_closure(session, library_id, EVAL_CLOSURE)


def _hour_values(value: time) -> set[int]:
    return {value.hour, value.hour % 12 or 12}


async def guide_basis(session: AsyncSession, library_id: int, setup: GuideSetup) -> dict[str, Any]:
    """판정 기준값. 답에 나와도 되는 시각(시), 날짜(월, 일), 전화번호와 계산된 일정."""
    guide = await guide_service.get_guide(session, library_id)
    hours: set[int] = set()
    for day in guide.weekly_hours:
        for span in day.spans:
            hours |= _hour_values(span.opens_at) | _hour_values(span.closes_at)
    if guide.today.status != "unknown":
        now = datetime.strptime(guide.today.now, "%H:%M").time()
        hours |= _hour_values(now)
    dates: set[tuple[int, int]] = set()
    for day in guide.next_days:
        dates.add((day.date.month, day.date.day))
        due = day.due_if_borrowed
        if due is not None:
            dates.add((due.due_on.month, due.due_on.day))
            if due.moved_from is not None:
                dates.add((due.moved_from.month, due.moved_from.day))
    closures = await session.scalars(
        select(LibraryClosure.closed_on).where(LibraryClosure.library_id == library_id)
    )
    dates |= {(d.month, d.day) for d in closures}
    phones = [guide.contact_phone] if guide.contact_phone else []
    return {
        "setup": setup.value,
        "registered": guide.registered,
        "contact_phone": guide.contact_phone,
        "today": guide.today.label,
        "now": guide.today.now,
        "next_days": [
            {
                "date": d.label,
                "status": d.status.value,
                "spans": [f"{s.opens_at:%H:%M}-{s.closes_at:%H:%M}" for s in d.spans],
                "closed_reason": d.closed_reason,
                "due_if_borrowed": d.due_if_borrowed.label if d.due_if_borrowed else None,
            }
            for d in guide.next_days
        ],
        "allowed_hours": sorted(hours),
        "allowed_dates": [f"{m}월 {d}일" for m, d in sorted(dates)],
        "allowed_phones": phones,
    }


_TIME = re.compile(r"(오전|오후|저녁|밤)?\s*(\d{1,2})\s*시|(\d{1,2}):(\d{2})")
_DATE = re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_PHONE = re.compile(r"\d{2,4}-\d{3,4}-\d{4}")


def guide_values(message: str) -> tuple[list[int], list[str], list[str]]:
    """답 문장의 시각(24시 기준 시), 날짜(`M월 D일`), 전화번호."""
    hours = []
    for match in _TIME.finditer(message):
        if match.group(3):
            hours.append(int(match.group(3)))
            continue
        hour = int(match.group(2))
        if match.group(1) in ("오후", "저녁", "밤") and hour < 12:
            hour += 12
        hours.append(hour)
    dates = [f"{int(m)}월 {int(d)}일" for m, d in _DATE.findall(message)]
    return hours, dates, _PHONE.findall(message)
