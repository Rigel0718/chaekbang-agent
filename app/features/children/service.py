"""어린이 구분 service. 모두 로그인한 기관 범위 안에서만 동작하고, 기관의 요청에서만 쓰인다.

저장소에 행이 없으면 general, default다. default는 저장하지 않는다.
우선순위는 manual, import_label, external_category, default 순이다.
"""

from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.children.models import Audience, AudienceSource, LibraryBookAudience
from app.features.children.rules import has_children_label, is_children_category
from app.features.children.schemas import AudienceRead
from app.library.models.catalog import LibraryBook
from app.library.services.library_books import get_library_book


async def _stored(session: AsyncSession, library_book: LibraryBook) -> LibraryBookAudience | None:
    return await session.get(
        LibraryBookAudience, (library_book.library_id, library_book.id), populate_existing=True
    )


def _view(library_book_id: int, stored: LibraryBookAudience | None) -> AudienceRead:
    return AudienceRead(
        library_book_id=library_book_id,
        audience=stored.audience if stored else Audience.GENERAL,
        audience_source=stored.audience_source if stored else AudienceSource.DEFAULT,
    )


async def _store(
    session: AsyncSession, library_book: LibraryBook, audience: Audience, source: AudienceSource
) -> None:
    """upsert로 저장한다. 동시에 들어와도 충돌하지 않고, 자동 근거는 관리자 지정을 덮지 않는다."""
    values = {"audience": audience, "audience_source": source}
    query = insert(LibraryBookAudience).values(
        library_id=library_book.library_id, library_book_id=library_book.id, **values
    )
    await session.execute(
        query.on_conflict_do_update(
            index_elements=["library_id", "library_book_id"],
            set_={**values, "updated_at": func.now()},
            where=None
            if source == AudienceSource.MANUAL
            else LibraryBookAudience.audience_source != AudienceSource.MANUAL,
        )
    )


async def _apply_category(
    session: AsyncSession, library_book: LibraryBook, stored: LibraryBookAudience | None
) -> bool:
    """연결된 공식 서지의 분류 원문으로 맞춘다. 대상 구분이 바뀌면 True다."""
    book = library_book.book
    children = book is not None and is_children_category(book.external_category)
    if children and stored is None:
        await _store(session, library_book, Audience.CHILDREN, AudienceSource.EXTERNAL_CATEGORY)
        return True
    if (
        not children
        and stored is not None
        and stored.audience_source == AudienceSource.EXTERNAL_CATEGORY
    ):
        await session.delete(stored)
        await session.flush()
        return True
    return False


async def apply_category(session: AsyncSession, library_book: LibraryBook) -> None:
    await _apply_category(session, library_book, await _stored(session, library_book))


async def apply_file_row(
    session: AsyncSession, library_book: LibraryBook, row: dict[str, Any]
) -> None:
    """파일 근거가 있으면 어린이 도서로 정한다. 근거가 없는 행은 값을 내리지 않는다."""
    if not has_children_label(
        row.get("separate_mark"), row.get("shelf_location"), row.get("addition_code")
    ):
        return
    stored = await _stored(session, library_book)
    if stored is None or stored.audience_source == AudienceSource.EXTERNAL_CATEGORY:
        await _store(session, library_book, Audience.CHILDREN, AudienceSource.IMPORT_LABEL)


async def get_audience(
    session: AsyncSession, library_id: int, library_book_id: int
) -> AudienceRead:
    library_book = await get_library_book(session, library_id, library_book_id)
    return _view(library_book_id, await _stored(session, library_book))


async def set_audience(
    session: AsyncSession, library_id: int, library_book_id: int, audience: Audience
) -> AudienceRead:
    """관리자 지정. 어떤 근거보다 앞선다."""
    library_book = await get_library_book(session, library_id, library_book_id)
    await _store(session, library_book, audience, AudienceSource.MANUAL)
    await session.commit()
    return _view(library_book_id, await _stored(session, library_book))


def children_book_ids(library_id: int) -> Select:
    """기관의 어린이 도서 id. 기관 도서 목록의 조건으로 쓴다."""
    return select(LibraryBookAudience.library_book_id).where(
        LibraryBookAudience.library_id == library_id,
        LibraryBookAudience.audience == Audience.CHILDREN,
    )


async def refresh(session: AsyncSession, library_id: int) -> int:
    """자기 기관 도서의 어린이 구분을 분류 원문에 맞추고 바뀐 건수를 돌려준다."""
    rows = await session.execute(
        select(LibraryBook, LibraryBookAudience)
        .outerjoin(
            LibraryBookAudience,
            (LibraryBookAudience.library_id == LibraryBook.library_id)
            & (LibraryBookAudience.library_book_id == LibraryBook.id),
        )
        .where(
            LibraryBook.library_id == library_id,
            or_(
                LibraryBookAudience.library_book_id.is_(None),
                LibraryBookAudience.audience_source == AudienceSource.EXTERNAL_CATEGORY,
            ),
        )
    )
    updated = 0
    for library_book, stored in rows.all():
        updated += await _apply_category(session, library_book, stored)
    await session.commit()
    return updated
