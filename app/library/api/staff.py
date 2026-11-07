from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.schemas import Page, Pagination, page_of
from app.library.deps import AdminStaff, Session
from app.library.schemas.staff import StaffCreate, StaffRead, StaffUpdate
from app.library.services import staff as staff_service

router = APIRouter(prefix="/staff", tags=["staff"])


@router.get("", response_model=Page[StaffRead])
async def list_staff(staff: AdminStaff, session: Session, page: Annotated[Pagination, Query()]):
    items, total = await staff_service.list_staff(
        session, staff.library_id, limit=page.limit, offset=page.offset
    )
    return page_of(StaffRead, items, total, page)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=StaffRead)
async def create_staff(data: StaffCreate, staff: AdminStaff, session: Session):
    return await staff_service.create_staff(session, staff.library_id, data)


@router.patch("/{staff_id}", response_model=StaffRead)
async def update_staff(staff_id: int, data: StaffUpdate, staff: AdminStaff, session: Session):
    return await staff_service.update_staff(
        session, staff.library_id, staff.staff_id, staff_id, data
    )
