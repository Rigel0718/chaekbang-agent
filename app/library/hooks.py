"""기관 개별 기능의 접점. 공통 코드는 기능을 이름으로 부르지 않고 사건만 알린다.

기능은 app/main.py에서 등록한다. 등록된 기능이 없어도 공통은 그대로 동작한다.
운영자 실행의 연결은 기관의 요청이 아니므로 알리지 않는다.
"""

from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.library.models.catalog import LibraryBook


class LibraryBookHook(Protocol):
    async def official_changed(self, session: AsyncSession, library_book: LibraryBook) -> None:
        """기관의 요청으로 공식 서지 연결이 정해졌다. 기관 도서는 저장돼 있다."""
        ...

    async def row_applied(
        self, session: AsyncSession, library_book: LibraryBook, row: dict[str, Any]
    ) -> None:
        """가져오기 행을 적용했다. 행에는 인식한 파일 값이 들어 있다."""
        ...


_hooks: list[LibraryBookHook] = []


def register_hook(hook: LibraryBookHook) -> None:
    _hooks.append(hook)


async def notify_official_changed(session: AsyncSession, library_book: LibraryBook) -> None:
    for hook in _hooks:
        await hook.official_changed(session, library_book)


async def notify_row_applied(
    session: AsyncSession, library_book: LibraryBook, row: dict[str, Any]
) -> None:
    for hook in _hooks:
        await hook.row_applied(session, library_book, row)
