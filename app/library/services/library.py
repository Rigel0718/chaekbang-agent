"""기관 정보 service."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.library.models.library import Library
from app.library.schemas.library import LibraryUpdate


async def get_library(session: AsyncSession, library_id: int) -> Library:
    library = await session.get(Library, library_id)
    assert library is not None  # 토큰으로 정해진 기관이라 항상 있다
    return library


async def update_library(session: AsyncSession, library_id: int, data: LibraryUpdate) -> Library:
    library = await get_library(session, library_id)
    for field, value in data.changes().items():
        setattr(library, field, value)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError("이미 쓰는 기관 이름입니다") from exc
    await session.refresh(library)
    return library
