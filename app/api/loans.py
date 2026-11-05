from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core import clock
from app.core.deps import AdminStaff, CurrentStaff, Session
from app.models.circulation import Loan
from app.schemas.circulation import LoanCreate, LoanRead, LoanReturn
from app.schemas.common import Page, Pagination
from app.services import loans
from app.services.loans import LoanFilter

router = APIRouter(prefix="/loans", tags=["loans"])


def _view(loan: Loan) -> LoanRead:
    return LoanRead(
        id=loan.id,
        holding_id=loan.holding_id,
        accession_number=loan.holding.accession_number,
        book_id=loan.holding.book_id,
        title=loan.holding.book.title,
        member_number=loan.member.member_number if loan.member else None,
        loaned_on=loan.loaned_on,
        due_on=loan.due_on,
        returned_on=loan.returned_on,
        overdue=loans.is_overdue(loan, clock.today()),
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=LoanRead)
async def create_loan(data: LoanCreate, staff: CurrentStaff, session: Session):
    """키오스크와 관리자 모두 쓴다."""
    loan = await loans.create_loan(
        session, staff.library_id, data.accession_number, data.member_number
    )
    return _view(loan)


@router.post("/return", response_model=LoanRead)
async def return_loan(data: LoanReturn, staff: CurrentStaff, session: Session):
    """등록번호로 반납한다. 키오스크와 관리자 모두 쓴다."""
    return _view(await loans.return_loan(session, staff.library_id, data.accession_number))


@router.get("", response_model=Page[LoanRead])
async def list_loans(
    staff: AdminStaff,
    session: Session,
    page: Annotated[Pagination, Query()],
    status: LoanFilter | None = None,
):
    rows, total = await loans.list_loans(
        session, staff.library_id, limit=page.limit, offset=page.offset, status=status
    )
    return Page[LoanRead](
        items=[_view(r) for r in rows], total=total, limit=page.limit, offset=page.offset
    )
