from fastapi import APIRouter

from app.library.deps import AdminStaff, CurrentStaff, Session
from app.library.schemas.library import LibraryRead, LibraryUpdate
from app.library.services import library

router = APIRouter(prefix="/library", tags=["library"])


@router.get("", response_model=LibraryRead)
async def get_library(staff: CurrentStaff, session: Session):
    return await library.get_library(session, staff.library_id)


@router.patch("", response_model=LibraryRead)
async def update_library(data: LibraryUpdate, staff: AdminStaff, session: Session):
    return await library.update_library(session, staff.library_id, data)
