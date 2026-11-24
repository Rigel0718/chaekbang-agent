from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.schemas import Page, Pagination, page_of
from app.library.deps import AdminStaff, CurrentMember, CurrentStaff, Session
from app.library.models.book_request import BookRequestStatus
from app.library.schemas.book_request import (
    BookRequestAdminRead,
    BookRequestCreate,
    BookRequestRead,
    BookRequestUpdate,
)
from app.library.services import book_requests

router = APIRouter(prefix="/book-requests", tags=["book-requests"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BookRequestRead)
async def create_request(
    data: BookRequestCreate, staff: CurrentStaff, member: CurrentMember, session: Session
):
    """희망도서를 신청한다. 키오스크와 관리자 모두 쓴다. 신청 회원은 회원 세션이 정한다."""
    return await book_requests.create_request(session, staff.library_id, member.member_id, data)


@router.get("", response_model=Page[BookRequestAdminRead])
async def list_requests(
    staff: AdminStaff,
    session: Session,
    page: Annotated[Pagination, Query()],
    status: BookRequestStatus | None = None,
):
    rows, total = await book_requests.list_requests(
        session, staff.library_id, limit=page.limit, offset=page.offset, status=status
    )
    return page_of(BookRequestAdminRead, rows, total, page)


@router.patch("/{request_id}", response_model=BookRequestAdminRead)
async def close_request(
    request_id: int, data: BookRequestUpdate, staff: AdminStaff, session: Session
):
    """처리했다고 닫는다. `requested`로 되돌리지 않는다."""
    return await book_requests.close_request(session, staff.library_id, request_id)
