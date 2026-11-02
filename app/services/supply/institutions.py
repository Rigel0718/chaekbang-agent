"""기관 service. 납품 목록과 견적서가 기관 단위로 묶인다."""

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supply import Institution, InstitutionOrder, InstitutionType, QuoteDraft
from app.schemas.supply import InstitutionCreate, InstitutionUpdate
from app.services.errors import ConflictError, NotFoundError


async def create_institution(session: AsyncSession, data: InstitutionCreate) -> Institution:
    institution = Institution(**data.model_dump())
    session.add(institution)
    await session.commit()
    await session.refresh(institution)
    return institution


async def get_institution(session: AsyncSession, institution_id: int) -> Institution:
    institution = await session.get(Institution, institution_id)
    if institution is None:
        raise NotFoundError(f"기관을 찾을 수 없습니다: {institution_id}")
    return institution


async def list_institutions(
    session: AsyncSession,
    *,
    limit: int,
    offset: int,
    type: InstitutionType | None = None,
) -> tuple[list[Institution], int]:
    query = select(Institution)
    if type is not None:
        query = query.where(Institution.type == type)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.scalars(query.order_by(Institution.id).limit(limit).offset(offset))
    return list(rows), total or 0


async def update_institution(
    session: AsyncSession, institution_id: int, data: InstitutionUpdate
) -> Institution:
    institution = await get_institution(session, institution_id)
    for field, value in data.changes().items():
        setattr(institution, field, value)
    await session.commit()
    await session.refresh(institution)
    return institution


async def delete_institution(session: AsyncSession, institution_id: int) -> None:
    institution = await get_institution(session, institution_id)
    referenced = await session.scalar(
        select(
            or_(
                exists().where(InstitutionOrder.institution_id == institution_id),
                exists().where(QuoteDraft.institution_id == institution_id),
            )
        )
    )
    if referenced:
        raise ConflictError(
            f"납품 목록이나 견적서가 있는 기관은 삭제할 수 없습니다: {institution_id}"
        )
    await session.delete(institution)
    await session.commit()
