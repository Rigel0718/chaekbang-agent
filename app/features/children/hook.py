"""기관 공통의 사건을 어린이 구분으로 잇는다."""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.features.children import service
from app.library.models.catalog import LibraryBook


class ChildrenHook:
    async def official_changed(self, session: AsyncSession, library_book: LibraryBook) -> None:
        await service.apply_category(session, library_book)

    async def row_applied(
        self, session: AsyncSession, library_book: LibraryBook, row: dict[str, Any]
    ) -> None:
        await service.apply_file_row(session, library_book, row)
