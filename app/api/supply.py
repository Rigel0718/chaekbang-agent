from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.models.supply import InstitutionType
from app.schemas.common import Page, Pagination
from app.schemas.supply import InstitutionCreate, InstitutionRead, InstitutionUpdate
from app.services.supply import institutions

router = APIRouter(tags=["supply"])

Session = Annotated[AsyncSession, Depends(get_session)]


@router.post("/institutions", status_code=status.HTTP_201_CREATED, response_model=InstitutionRead)
async def create_institution(data: InstitutionCreate, session: Session):
    return await institutions.create_institution(session, data)


@router.get("/institutions", response_model=Page[InstitutionRead])
async def list_institutions(
    session: Session,
    page: Annotated[Pagination, Query()],
    type: InstitutionType | None = None,
):
    items, total = await institutions.list_institutions(
        session, limit=page.limit, offset=page.offset, type=type
    )
    return Page[InstitutionRead](
        items=[InstitutionRead.model_validate(i) for i in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/institutions/{institution_id}", response_model=InstitutionRead)
async def get_institution(institution_id: int, session: Session):
    return await institutions.get_institution(session, institution_id)


@router.patch("/institutions/{institution_id}", response_model=InstitutionRead)
async def update_institution(institution_id: int, data: InstitutionUpdate, session: Session):
    return await institutions.update_institution(session, institution_id, data)


@router.delete("/institutions/{institution_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_institution(institution_id: int, session: Session) -> None:
    await institutions.delete_institution(session, institution_id)
