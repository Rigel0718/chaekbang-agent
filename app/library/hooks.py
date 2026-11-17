"""기관 개별 기능의 접점. 공통 코드는 기능을 이름으로 부르지 않고 사건만 알린다.

기능은 app/main.py에서 등록한다. 등록된 기능이 없어도 공통은 그대로 동작한다.
운영자 실행의 연결은 기관의 요청이 아니므로 알리지 않는다.

관련 책 범위 제공자(`RelatedScope`)는 사건이 아니라 조건을 돌려준다. 기준 책(들)을 받아 결과를 좁힐
기관 도서 id 조건을 주거나 None을 준다. 공통 코드는 조건의 뜻을 모르고, 등록된 조건을 모두 건다.
"""

from collections.abc import Sequence
from typing import Any, Protocol

from sqlalchemy import Select
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


class RelatedScope(Protocol):
    async def __call__(
        self, session: AsyncSession, library_id: int, base_ids: Sequence[int]
    ) -> Select | None:
        """기준 책(최근 기록이면 기록 책들)에 따라 관련 책 결과를 좁힐 기관 도서 id 조건."""
        ...


_related_scopes: list[RelatedScope] = []


def register_related_scope(scope: RelatedScope) -> None:
    """같은 제공자를 두 번 등록해도 한 번만 건다(서버와 평가 진입점이 함께 import될 때)."""
    if scope not in _related_scopes:
        _related_scopes.append(scope)


async def related_scope_conditions(
    session: AsyncSession, library_id: int, base_ids: Sequence[int]
) -> list[Select]:
    """등록된 제공자가 준 조건. 조건을 주지 않은 제공자는 빠진다."""
    conditions = []
    for scope in _related_scopes:
        condition = await scope(session, library_id, base_ids)
        if condition is not None:
            conditions.append(condition)
    return conditions
