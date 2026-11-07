"""기관 도서 service. REST 라우터와 이후 에이전트 tool(search_collection 등)이 함께 쓴다.

모든 함수는 로그인한 기관(library_id) 범위 안에서만 동작하고, 공식 서지(books)는 읽기만 한다.
"""

from dataclasses import dataclass

from sqlalchemy import Select, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import (
    BIBLIOGRAPHIC_FIELDS,
    AcquisitionType,
    Audience,
    AudienceSource,
    Book,
    Holding,
    HoldingStatus,
    LibraryBook,
)
from app.schemas.catalog import LibraryBookCreate, LibraryBookUpdate
from app.services.errors import ConflictError
from app.services.tenancy import get_owned

LABEL = "도서"


@dataclass(frozen=True)
class LibraryBookCounts:
    library_book: LibraryBook
    holding_count: int
    available_count: int


def _duplicate_isbn(isbn: str) -> ConflictError:
    return ConflictError(f"이미 등록된 ISBN입니다: {isbn}")


async def _ensure_isbn_free(
    session: AsyncSession, library_id: int, isbn: str, *, except_id: int | None = None
) -> None:
    query = select(LibraryBook.id).where(
        LibraryBook.library_id == library_id, LibraryBook.isbn == isbn
    )
    if except_id is not None:
        query = query.where(LibraryBook.id != except_id)
    if await session.scalar(query) is not None:
        raise _duplicate_isbn(isbn)


async def _commit(session: AsyncSession, isbn: str | None) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        # 동시에 같은 ISBN이 들어온 경우 UNIQUE 제약이 막는다.
        await session.rollback()
        raise _duplicate_isbn(isbn or "") from exc


async def link_official(session: AsyncSession, library_book: LibraryBook) -> None:
    """ISBN이 같은 공식 서지에 연결한다. 없으면 연결을 비운다."""
    if library_book.isbn is None:
        library_book.book = None
        return
    library_book.book = await session.scalar(select(Book).where(Book.isbn == library_book.isbn))


async def create_library_book(
    session: AsyncSession, library_id: int, data: LibraryBookCreate
) -> LibraryBook:
    if data.isbn is not None:
        await _ensure_isbn_free(session, library_id, data.isbn)
    library_book = LibraryBook(library_id=library_id, **data.model_dump(exclude={"audience"}))
    if data.audience is not None:
        library_book.audience = data.audience
        library_book.audience_source = AudienceSource.MANUAL
    await link_official(session, library_book)
    session.add(library_book)
    await _commit(session, data.isbn)
    await session.refresh(library_book)
    return library_book


async def get_library_book(
    session: AsyncSession, library_id: int, library_book_id: int
) -> LibraryBook:
    return await get_owned(session, LibraryBook, library_id, library_book_id, label=LABEL)


def _with_counts(library_id: int) -> Select:
    counts = (
        select(
            Holding.library_book_id,
            func.count().label("holding_count"),
            func.count().filter(Holding.status == HoldingStatus.AVAILABLE).label("available_count"),
        )
        .where(Holding.library_id == library_id, Holding.status != HoldingStatus.WITHDRAWN)
        .group_by(Holding.library_book_id)
        .subquery()
    )
    return (
        select(
            LibraryBook,
            func.coalesce(counts.c.holding_count, 0),
            func.coalesce(counts.c.available_count, 0),
        )
        .outerjoin(counts, counts.c.library_book_id == LibraryBook.id)
        .where(LibraryBook.library_id == library_id)
    )


async def get_library_book_with_counts(
    session: AsyncSession, library_id: int, library_book_id: int
) -> LibraryBookCounts:
    await get_library_book(session, library_id, library_book_id)
    row = (
        await session.execute(_with_counts(library_id).where(LibraryBook.id == library_book_id))
    ).one()
    return LibraryBookCounts(*row)


async def list_library_books(
    session: AsyncSession,
    library_id: int,
    *,
    limit: int,
    offset: int,
    isbn: str | None = None,
    held: bool = False,
    audience: Audience | None = None,
) -> tuple[list[LibraryBookCounts], int]:
    """held=True면 제적이 아닌 사본이 하나 이상 있는 도서만."""
    query = _with_counts(library_id)
    if isbn is not None:
        query = query.where(LibraryBook.isbn == isbn)
    if audience is not None:
        query = query.where(LibraryBook.audience == audience)
    if held:
        query = query.where(
            exists().where(
                Holding.library_book_id == LibraryBook.id,
                Holding.status != HoldingStatus.WITHDRAWN,
            )
        )
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    # 정렬은 화면에 보이는 표시 값 기준이다.
    shown_title = func.coalesce(Book.title, LibraryBook.title)
    rows = await session.execute(
        query.outerjoin(Book, Book.id == LibraryBook.book_id)
        .order_by(shown_title, LibraryBook.id)
        .limit(limit)
        .offset(offset)
    )
    return [LibraryBookCounts(*row) for row in rows], total or 0


async def update_library_book(
    session: AsyncSession, library_id: int, library_book_id: int, data: LibraryBookUpdate
) -> LibraryBook:
    library_book = await get_library_book(session, library_id, library_book_id)
    changes = data.changes()
    if library_book.book_id is not None and set(changes) & set(BIBLIOGRAPHIC_FIELDS):
        raise ConflictError("공식 서지에 연결된 도서는 ISBN과 대상 구분만 고칠 수 있습니다")
    if "isbn" in changes:
        new_isbn = changes["isbn"]
        if new_isbn is None and library_book.isbn is not None:
            has_purchased = await session.scalar(
                select(
                    exists().where(
                        Holding.library_book_id == library_book_id,
                        Holding.acquisition_type == AcquisitionType.PURCHASED,
                    )
                )
            )
            if has_purchased:
                raise ConflictError("매입·납품 사본이 있는 도서는 ISBN을 비울 수 없습니다")
        elif new_isbn is not None:
            await _ensure_isbn_free(session, library_id, new_isbn, except_id=library_book_id)
    if "audience" in changes:
        library_book.audience_source = AudienceSource.MANUAL
    for field, value in changes.items():
        setattr(library_book, field, value)
    if "isbn" in changes:
        await link_official(session, library_book)
    await _commit(session, changes.get("isbn"))
    await session.refresh(library_book)
    return library_book


async def delete_library_book(session: AsyncSession, library_id: int, library_book_id: int) -> None:
    """제적 사본을 포함해 사본이 있으면 삭제를 거부한다."""
    library_book = await get_library_book(session, library_id, library_book_id)
    if await session.scalar(select(exists().where(Holding.library_book_id == library_book_id))):
        raise ConflictError("소장 사본이 있는 도서는 삭제할 수 없습니다")
    await session.delete(library_book)
    await session.commit()
