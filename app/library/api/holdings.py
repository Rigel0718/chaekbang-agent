from typing import Annotated

from fastapi import APIRouter, Query, status

from app.core.deps import AdminStaff, CurrentStaff, Session
from app.models.catalog import Holding, HoldingStatus
from app.schemas.catalog import HoldingCreate, HoldingRead, HoldingUpdate
from app.schemas.common import Page, Pagination
from app.services import holdings

router = APIRouter(prefix="/holdings", tags=["holdings"])


def _view(holding: Holding) -> HoldingRead:
    return HoldingRead.model_validate(
        {
            **{f: getattr(holding, f) for f in HoldingRead.model_fields if hasattr(holding, f)},
            "isbn": holding.library_book.isbn,
            "title": holding.library_book.shown("title"),
            "author": holding.library_book.shown("author"),
            "missing_fields": holdings.missing_fields(holding),
        }
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=HoldingRead)
async def create_holding(data: HoldingCreate, staff: AdminStaff, session: Session):
    return _view(await holdings.create_holding(session, staff.library_id, data))


@router.get("", response_model=Page[HoldingRead])
async def list_holdings(
    staff: CurrentStaff,
    session: Session,
    page: Annotated[Pagination, Query()],
    library_book_id: int | None = None,
    status: HoldingStatus | None = None,
    incomplete: Annotated[bool, Query(description="true면 빠진 정보가 있는 사본만")] = False,
):
    rows, total = await holdings.list_holdings(
        session,
        staff.library_id,
        limit=page.limit,
        offset=page.offset,
        library_book_id=library_book_id,
        status=status,
        incomplete=incomplete,
    )
    return Page[HoldingRead](
        items=[_view(h) for h in rows], total=total, limit=page.limit, offset=page.offset
    )


@router.get("/{holding_id}", response_model=HoldingRead)
async def get_holding(holding_id: int, staff: CurrentStaff, session: Session):
    return _view(await holdings.get_holding(session, staff.library_id, holding_id))


@router.patch("/{holding_id}", response_model=HoldingRead)
async def update_holding(holding_id: int, data: HoldingUpdate, staff: AdminStaff, session: Session):
    return _view(await holdings.update_holding(session, staff.library_id, holding_id, data))


@router.delete("/{holding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_holding(holding_id: int, staff: AdminStaff, session: Session) -> None:
    await holdings.delete_holding(session, staff.library_id, holding_id)
