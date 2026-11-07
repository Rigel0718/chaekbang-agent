from typing import Annotated

from fastapi import APIRouter, Query

from app.core.schemas import Page, Pagination
from app.features.children import service
from app.features.children.schemas import AudienceRead, AudienceUpdate, RefreshResult
from app.library.api.library_books import book_view
from app.library.deps import AdminStaff, CurrentStaff, Session
from app.library.schemas.catalog import LibraryBookWithHoldings
from app.library.services import library_books

router = APIRouter(prefix="/children", tags=["children"])


@router.get("/books", response_model=Page[LibraryBookWithHoldings])
async def list_children_books(
    staff: CurrentStaff, session: Session, page: Annotated[Pagination, Query()]
):
    rows, total = await library_books.list_library_books(
        session,
        staff.library_id,
        limit=page.limit,
        offset=page.offset,
        within=service.children_book_ids(staff.library_id),
    )
    return Page[LibraryBookWithHoldings](
        items=[book_view(r) for r in rows], total=total, limit=page.limit, offset=page.offset
    )


@router.get("/books/{library_book_id}", response_model=AudienceRead)
async def get_audience(library_book_id: int, staff: CurrentStaff, session: Session):
    return await service.get_audience(session, staff.library_id, library_book_id)


@router.put("/books/{library_book_id}", response_model=AudienceRead)
async def set_audience(
    library_book_id: int, data: AudienceUpdate, staff: AdminStaff, session: Session
):
    return await service.set_audience(session, staff.library_id, library_book_id, data.audience)


@router.post("/refresh", response_model=RefreshResult)
async def refresh(staff: AdminStaff, session: Session):
    """공식 서지가 채워진 뒤 자기 기관의 어린이 구분을 갱신한다."""
    return RefreshResult(updated=await service.refresh(session, staff.library_id))
