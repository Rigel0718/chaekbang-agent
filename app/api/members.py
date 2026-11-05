from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.deps import AdminStaff, Session
from app.schemas.circulation import MemberCreate, MemberRead, MemberUpdate
from app.schemas.common import Page, Pagination, page_of
from app.services import members

router = APIRouter(prefix="/members", tags=["members"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=MemberRead)
async def create_member(data: MemberCreate, staff: AdminStaff, session: Session):
    return await members.create_member(session, staff.library_id, data)


@router.get("", response_model=Page[MemberRead])
async def list_members(
    staff: AdminStaff,
    session: Session,
    page: Annotated[Pagination, Query()],
    q: Annotated[str | None, Query(description="이름이나 회원번호 일부")] = None,
):
    rows, total = await members.list_members(
        session, staff.library_id, limit=page.limit, offset=page.offset, q=q
    )
    return page_of(MemberRead, rows, total, page)


@router.get("/{member_id}", response_model=MemberRead)
async def get_member(member_id: int, staff: AdminStaff, session: Session):
    return await members.get_member(session, staff.library_id, member_id)


@router.patch("/{member_id}", response_model=MemberRead)
async def update_member(member_id: int, data: MemberUpdate, staff: AdminStaff, session: Session):
    return await members.update_member(session, staff.library_id, member_id, data)


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_member(member_id: int, staff: AdminStaff, session: Session) -> None:
    await members.delete_member(session, staff.library_id, member_id)
