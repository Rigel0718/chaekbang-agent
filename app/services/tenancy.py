"""기관 범위 강제 도우미. 기관 데이터는 항상 로그인한 기관(library_id)으로 거른다."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.errors import NotFoundError


async def get_owned[M](
    session: AsyncSession, model: type[M], library_id: int, id: int, *, label: str
) -> M:
    """같은 기관의 행만 돌려준다. 다른 기관의 행은 없는 것과 같이 NotFoundError(404)."""
    row = await session.scalar(
        select(model).where(model.id == id, model.library_id == library_id)  # type: ignore[attr-defined]
    )
    if row is None:
        raise NotFoundError(f"{label}을(를) 찾을 수 없습니다: {id}")
    return row
