"""장서·대출 분석 service. 운영 에이전트 tool이 부르고, 나중에 REST도 같은 함수를 부른다.

숫자는 모두 여기서 센다. 규칙(design `add-admin-agent` 결정 3·5·6·7):
- 분야는 `analytics/fields.py`가 정한다. 그룹에는 값이 0인 분야도 늘 넣어 합이 전체와 같다.
- 장서 수는 제적 사본을 빼고 따로 센다. 분실·훼손·대출 중은 센다.
- 대출은 빌린 날(`loaned_on`)이 기간 안이면 센다. 제적된 사본의 대출도 센다.
- 지금 대출 중·연체 중은 기간과 상관없이 오늘 기준이다. 책 필터는 건다.
- 목록과 순위는 전체 수와 잘림을 함께 낸다. 같은 수는 건수 → 서명 가나다순 → id다.
회원(`members`)과 기증자(`holdings.donor`)는 읽지 않는다.
"""

from collections.abc import Sequence
from datetime import datetime, time
from zoneinfo import ZoneInfo

from sqlalchemy import Exists, and_, distinct, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core import clock
from app.core.config import get_settings
from app.core.errors import InvalidRequestError
from app.core.text import korean_order
from app.library.analytics.axes import AnalysisAxis
from app.library.analytics.periods import PeriodPreset, resolve_period
from app.library.analytics.scope import (
    ACQUISITION,
    ACQUISITION_LABELS,
    FIELD,
    STATUS,
    STATUS_LABELS,
    BookFilter,
    Grouping,
    book_facts,
    book_grouping,
    filter_conditions,
)
from app.library.models.catalog import Holding, HoldingStatus
from app.library.models.circulation import Loan
from app.library.schemas.analytics import (
    LIMIT_MAX,
    TOP_N_MAX,
    BookRanking,
    CollectionStatus,
    CountGroup,
    CurrentLoans,
    HoldingItem,
    HoldingList,
    LoanGroup,
    LoanStats,
    RankedBook,
    UnborrowedBook,
    UnborrowedBooks,
)

LISTABLE_STATUSES = (HoldingStatus.LOST, HoldingStatus.DAMAGED, HoldingStatus.ON_LOAN)
BOOK = "book"


def _check_count(name: str, value: int, maximum: int) -> None:
    if not 1 <= value <= maximum:
        raise InvalidRequestError(f"{name}는 1~{maximum}입니다")


def _check_axes(book_filter: BookFilter, group_by: str | None, axes: Sequence[AnalysisAxis]):
    known = {a.name: a for a in axes}
    for name, value in book_filter.axes.items():
        if name not in known or value not in known[name].values:
            raise InvalidRequestError(f"알 수 없는 필터 값: {name}={value}")
    if group_by is not None and group_by not in (FIELD, STATUS, ACQUISITION, BOOK, *known):
        raise InvalidRequestError(f"묶을 수 없는 값: {group_by}")


def _holding_grouping(facts, key: str, axes: Sequence[AnalysisAxis]) -> Grouping:
    if key == STATUS:
        return Grouping(
            key, Holding.status, tuple((s.value, label) for s, label in STATUS_LABELS.items())
        )
    if key == ACQUISITION:
        return Grouping(
            key,
            Holding.acquisition_type,
            tuple((a.value, label) for a, label in ACQUISITION_LABELS.items()),
        )
    return book_grouping(facts, key, axes)


def _round(value: float) -> float:
    return float(f"{value:.1f}")


async def collection_status(
    session: AsyncSession,
    library_id: int,
    *,
    group_by: str | None,
    book_filter: BookFilter,
    axes: Sequence[AnalysisAxis] = (),
) -> CollectionStatus:
    if group_by == BOOK:
        raise InvalidRequestError("장서 현황은 책으로 묶지 않습니다")
    _check_axes(book_filter, group_by, axes)
    facts = book_facts(library_id, axes)
    base = and_(
        Holding.library_id == library_id,
        Holding.library_book_id == facts.c.library_book_id,
        *filter_conditions(facts, book_filter),
    )
    kept = Holding.status != HoldingStatus.WITHDRAWN
    copies = func.count().filter(kept)
    titles = func.count(distinct(Holding.library_book_id)).filter(kept)
    withdrawn = func.count().filter(Holding.status == HoldingStatus.WITHDRAWN)
    total = (await session.execute(select(copies, titles, withdrawn).where(base))).one()

    groups: list[CountGroup] = []
    if group_by is not None:
        grouping = _holding_grouping(facts, group_by, axes)
        rows = await session.execute(
            select(grouping.column, copies, titles).where(base, kept).group_by(grouping.column)
        )
        counted = {str(key): (c, t) for key, c, t in rows}
        groups = [
            CountGroup(
                key=value,
                label=label,
                copies=counted.get(value, (0, 0))[0],
                titles=counted.get(value, (0, 0))[1],
            )
            for value, label in grouping.values
        ]
    return CollectionStatus(
        group_by=group_by,
        copies=total[0],
        titles=total[1],
        withdrawn_copies=total[2],
        groups=groups,
    )


async def holdings_by_status(
    session: AsyncSession,
    library_id: int,
    *,
    status: HoldingStatus,
    book_filter: BookFilter,
    axes: Sequence[AnalysisAxis] = (),
    limit: int,
) -> HoldingList:
    if status not in LISTABLE_STATUSES:
        raise InvalidRequestError("상태는 분실, 훼손, 대출 중 중 하나입니다")
    _check_count("limit", limit, LIMIT_MAX)
    _check_axes(book_filter, None, axes)
    facts = book_facts(library_id, axes)
    where = and_(
        Holding.library_id == library_id,
        Holding.library_book_id == facts.c.library_book_id,
        Holding.status == status,
        *filter_conditions(facts, book_filter),
    )
    total = await session.scalar(select(func.count()).where(where)) or 0
    rows = await session.execute(
        select(
            facts.c.library_book_id,
            facts.c.title,
            facts.c.author,
            Holding.accession_number,
            Holding.call_number,
            Holding.status,
            Holding.updated_at,
            Holding.last_synced_at,
        )
        .where(where)
        .order_by(korean_order(facts.c.title), Holding.id)
        .limit(limit)
    )
    items = [HoldingItem.model_validate(row, from_attributes=True) for row in rows]
    return HoldingList(
        status=status, total=total, shown=len(items), truncated=total > len(items), items=items
    )


def _loan_scope(library_id: int, facts, book_filter: BookFilter):
    return and_(
        Loan.library_id == library_id,
        Holding.id == Loan.holding_id,
        Holding.library_id == library_id,
        Holding.library_book_id == facts.c.library_book_id,
        *filter_conditions(facts, book_filter),
    )


def _in_collection(library_id: int, library_book_id) -> Exists:
    """제적 아닌 사본이 있다. 바깥 쿼리의 사본과 섞이지 않게 별칭으로 센다."""
    other = aliased(Holding)
    return exists().where(
        other.library_id == library_id,
        other.library_book_id == library_book_id,
        other.status != HoldingStatus.WITHDRAWN,
    )


async def _current_loans(session: AsyncSession, scope) -> CurrentLoans:
    today = clock.today()
    active = Loan.returned_on.is_(None)
    row = (
        await session.execute(
            select(
                func.count().filter(active),
                func.count().filter(active, Loan.due_on < today),
            ).where(scope)
        )
    ).one()
    return CurrentLoans(on_loan=row[0], overdue=row[1])


async def _field_copies(session: AsyncSession, library_id: int, facts, book_filter, grouping):
    rows = await session.execute(
        select(grouping.column, func.count())
        .where(
            Holding.library_id == library_id,
            Holding.library_book_id == facts.c.library_book_id,
            Holding.status != HoldingStatus.WITHDRAWN,
            *filter_conditions(facts, book_filter),
        )
        .group_by(grouping.column)
    )
    return {str(key): n for key, n in rows}


async def _ranking(session: AsyncSession, library_id: int, facts, scope, in_period, top_n: int):
    loans = func.count().label("loans")
    total = await session.scalar(
        select(func.count(distinct(facts.c.library_book_id))).where(scope, in_period)
    )
    rows = await session.execute(
        select(
            facts.c.library_book_id,
            facts.c.title,
            facts.c.author,
            loans,
            _in_collection(library_id, facts.c.library_book_id).label("in_collection"),
        )
        .where(scope, in_period)
        .group_by(facts.c.library_book_id, facts.c.title, facts.c.author)
        .order_by(loans.desc(), korean_order(facts.c.title), facts.c.library_book_id)
        .limit(top_n)
    )
    items = [RankedBook.model_validate(row, from_attributes=True) for row in rows]
    total = total or 0
    return BookRanking(total=total, shown=len(items), truncated=total > len(items), items=items)


async def loan_stats(
    session: AsyncSession,
    library_id: int,
    *,
    period: PeriodPreset | None,
    month: int | None,
    group_by: str | None,
    book_filter: BookFilter,
    axes: Sequence[AnalysisAxis] = (),
    top_n: int,
) -> LoanStats:
    if group_by in (STATUS, ACQUISITION):
        raise InvalidRequestError("대출 통계는 분야, 책, 축으로만 묶습니다")
    _check_axes(book_filter, group_by, axes)
    _check_count("top_n", top_n, TOP_N_MAX)
    resolved = resolve_period(period, month, clock.today())
    facts = book_facts(library_id, axes)
    scope = _loan_scope(library_id, facts, book_filter)
    in_period = Loan.loaned_on.between(resolved.start, resolved.end)
    loans = await session.scalar(select(func.count()).where(scope, in_period)) or 0

    groups: list[LoanGroup] = []
    ranking = None
    if group_by == BOOK:
        ranking = await _ranking(session, library_id, facts, scope, in_period, top_n)
    elif group_by is not None:
        grouping = book_grouping(facts, group_by, axes)
        rows = await session.execute(
            select(grouping.column, func.count()).where(scope, in_period).group_by(grouping.column)
        )
        counted = {str(key): n for key, n in rows}
        copies = (
            await _field_copies(session, library_id, facts, book_filter, grouping)
            if group_by == FIELD
            else None
        )
        for value, label in grouping.values:
            n = counted.get(value, 0)
            c = copies.get(value, 0) if copies is not None else None
            groups.append(
                LoanGroup(
                    key=value,
                    label=label,
                    loans=n,
                    copies=c,
                    loans_per_copy=_round(n / c) if c else None,
                )
            )
    return LoanStats(
        period=resolved,
        group_by=group_by,
        loans=loans,
        groups=groups,
        ranking=ranking,
        current=await _current_loans(session, scope),
    )


def _local_midnight(day) -> datetime:
    return datetime.combine(day, time.min, tzinfo=ZoneInfo(get_settings().library_timezone))


async def unborrowed_books(
    session: AsyncSession,
    library_id: int,
    *,
    period: PeriodPreset | None,
    month: int | None,
    book_filter: BookFilter,
    axes: Sequence[AnalysisAxis] = (),
    limit: int,
) -> UnborrowedBooks:
    _check_count("limit", limit, LIMIT_MAX)
    _check_axes(book_filter, None, axes)
    resolved = resolve_period(period, month, clock.today())
    facts = book_facts(library_id, axes)
    copies = (
        select(func.count())
        .where(
            Holding.library_id == library_id,
            Holding.library_book_id == facts.c.library_book_id,
            Holding.status != HoldingStatus.WITHDRAWN,
        )
        .scalar_subquery()
    )
    borrowed = exists().where(
        Loan.library_id == library_id,
        Loan.holding_id == Holding.id,
        Holding.library_id == library_id,
        Holding.library_book_id == facts.c.library_book_id,
        Loan.loaned_on.between(resolved.start, resolved.end),
    )
    where = and_(
        _in_collection(library_id, facts.c.library_book_id),
        facts.c.created_at < _local_midnight(resolved.start),
        ~borrowed,
        *filter_conditions(facts, book_filter),
    )
    total = await session.scalar(select(func.count()).select_from(facts).where(where)) or 0
    rows = await session.execute(
        select(facts.c.library_book_id, facts.c.title, facts.c.author, copies.label("copies"))
        .where(where)
        .order_by(korean_order(facts.c.title), facts.c.library_book_id)
        .limit(limit)
    )
    items = [UnborrowedBook.model_validate(row, from_attributes=True) for row in rows]
    return UnborrowedBooks(
        period=resolved, total=total, shown=len(items), truncated=total > len(items), items=items
    )
