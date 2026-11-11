"""대출 service: 빌림·반납·대출 목록. 예약·연장·연체료는 만들지 않는다.

키오스크(이용자)와 관리자가 함께 쓰고, 이후 AI 사서의 create_loan·return_loan tool도 이 함수를 쓴다.
"""

from datetime import date
from enum import StrEnum

from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.errors import ConflictError, NotFoundError
from app.library.models.catalog import Holding, HoldingStatus
from app.library.models.circulation import Loan, Member
from app.library.models.library import Library, LoanMode
from app.library.services.guide import compute_due_date

DESK_ONLY = "이 도서관의 대출·반납은 데스크에서 해 주세요"


class LoanFilter(StrEnum):
    ACTIVE = "active"  # 반납 안 됨
    OVERDUE = "overdue"  # 반납 안 됐고 반납 예정일이 오늘보다 앞
    RETURNED = "returned"


async def _library_for_circulation(session: AsyncSession, library_id: int) -> Library:
    """가져오기 기관은 기존 대출 프로그램에서 대출하므로 여기서 처리하지 않는다."""
    library = await session.get(Library, library_id)
    assert library is not None
    if library.loan_mode == LoanMode.IMPORTED:
        raise ConflictError(DESK_ONLY)
    return library


async def _lock_holding(session: AsyncSession, library_id: int, accession_number: str) -> Holding:
    holding = await session.scalar(
        select(Holding)
        .where(Holding.library_id == library_id, Holding.accession_number == accession_number)
        .with_for_update(of=Holding)
    )
    if holding is None:
        raise NotFoundError(f"등록번호에 해당하는 책이 없습니다: {accession_number}")
    return holding


async def create_loan(
    session: AsyncSession, library_id: int, accession_number: str, member_number: str
) -> Loan:
    await _library_for_circulation(session, library_id)
    holding = await _lock_holding(session, library_id, accession_number)
    member = await session.scalar(
        select(Member).where(Member.library_id == library_id, Member.member_number == member_number)
    )
    if member is None:
        raise NotFoundError("회원번호를 확인해 주세요")
    if holding.status != HoldingStatus.AVAILABLE:
        raise ConflictError(f"지금 빌릴 수 없는 책입니다 (상태: {holding.status})")

    today = clock.today()
    # 안내와 같은 계산: 기본 대출 기간을 더하고, 휴관일이면 기관의 반납일 규칙을 따른다
    due = await compute_due_date(session, library_id, today)
    loan = Loan(
        library_id=library_id,
        holding_id=holding.id,
        member_id=member.id,
        loaned_on=today,
        due_on=due.due_on,
    )
    holding.status = HoldingStatus.ON_LOAN
    session.add(loan)
    try:
        await session.commit()
    except IntegrityError as exc:
        # 같은 사본에 반납 안 된 대출이 동시에 생기는 경우 부분 UNIQUE 인덱스가 막는다.
        await session.rollback()
        raise ConflictError("이미 대출 중인 책입니다") from exc
    return await get_loan(session, library_id, loan.id)


async def return_loan(session: AsyncSession, library_id: int, accession_number: str) -> Loan:
    """등록번호로 그 사본의 반납 안 된 대출을 반납한다. 회원번호는 받지 않는다."""
    await _library_for_circulation(session, library_id)
    holding = await _lock_holding(session, library_id, accession_number)
    loan = await session.scalar(
        select(Loan)
        .where(
            Loan.library_id == library_id,
            Loan.holding_id == holding.id,
            Loan.returned_on.is_(None),
        )
        .with_for_update(of=Loan)
    )
    if loan is None:
        raise ConflictError("대출 중인 책이 아닙니다")
    loan.returned_on = clock.today()
    holding.status = HoldingStatus.AVAILABLE
    await session.commit()
    return await get_loan(session, library_id, loan.id)


async def get_loan(session: AsyncSession, library_id: int, loan_id: int) -> Loan:
    loan = await session.scalar(
        select(Loan).where(Loan.id == loan_id, Loan.library_id == library_id)
    )
    if loan is None:
        raise NotFoundError(f"대출을 찾을 수 없습니다: {loan_id}")
    await session.refresh(loan)
    return loan


def _filtered(query: Select, status: LoanFilter | None, today: date) -> Select:
    if status == LoanFilter.ACTIVE:
        return query.where(Loan.returned_on.is_(None))
    if status == LoanFilter.OVERDUE:
        return query.where(Loan.returned_on.is_(None), Loan.due_on < today)
    if status == LoanFilter.RETURNED:
        return query.where(Loan.returned_on.is_not(None))
    return query


async def list_loans(
    session: AsyncSession,
    library_id: int,
    *,
    limit: int,
    offset: int,
    status: LoanFilter | None = None,
) -> tuple[list[Loan], int]:
    today = clock.today()
    base = _filtered(select(Loan).where(Loan.library_id == library_id), status, today)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = await session.scalars(
        base.order_by(Loan.loaned_on.desc(), Loan.id.desc()).limit(limit).offset(offset)
    )
    return list(rows.unique()), total or 0


def is_overdue(loan: Loan, today: date | None = None) -> bool:
    """연체는 저장하지 않고 조회할 때 계산한다."""
    return loan.returned_on is None and loan.due_on < (today or clock.today())
