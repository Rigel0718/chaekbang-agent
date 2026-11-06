"""도서 service. REST 라우터와 이후 에이전트 tool(search_collection 등)이 함께 쓴다.

도서는 기관 공통이지만, 조회 결과에는 로그인한 기관의 소장 권수와 대출 가능 권수를 붙인다.
"""

from dataclasses import dataclass

from sqlalchemy import Select, exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import (
    AcquisitionType,
    Audience,
    AudienceSource,
    Book,
    Holding,
    HoldingStatus,
)
from app.schemas.catalog import BookCreate, BookUpdate
from app.services.errors import ConflictError, NotFoundError


@dataclass(frozen=True)
class BookCounts:
    book: Book
    holding_count: int
    available_count: int


def _duplicate_isbn(isbn: str) -> ConflictError:
    return ConflictError(f"이미 등록된 ISBN입니다: {isbn}")


async def _ensure_isbn_free(session: AsyncSession, isbn: str, *, except_id: int | None = None):
    query = select(Book.id).where(Book.isbn == isbn)
    if except_id is not None:
        query = query.where(Book.id != except_id)
    if await session.scalar(query) is not None:
        raise _duplicate_isbn(isbn)


async def _commit(session: AsyncSession, isbn: str | None) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        # 동시에 같은 ISBN이 들어온 경우 UNIQUE 제약이 막는다.
        await session.rollback()
        raise _duplicate_isbn(isbn or "") from exc


async def create_book(session: AsyncSession, data: BookCreate) -> Book:
    if data.isbn is not None:
        await _ensure_isbn_free(session, data.isbn)
    values = data.model_dump(exclude={"audience"})
    book = Book(**values)
    if data.audience is not None:
        book.audience = data.audience
        book.audience_source = AudienceSource.MANUAL
    session.add(book)
    await _commit(session, data.isbn)
    await session.refresh(book)
    return book


async def get_book(session: AsyncSession, book_id: int) -> Book:
    book = await session.get(Book, book_id)
    if book is None:
        raise NotFoundError(f"도서를 찾을 수 없습니다: {book_id}")
    return book


def _with_counts(library_id: int) -> Select:
    counts = (
        select(
            Holding.book_id,
            func.count().label("holding_count"),
            func.count().filter(Holding.status == HoldingStatus.AVAILABLE).label("available_count"),
        )
        .where(Holding.library_id == library_id, Holding.status != HoldingStatus.WITHDRAWN)
        .group_by(Holding.book_id)
        .subquery()
    )
    return select(
        Book,
        func.coalesce(counts.c.holding_count, 0),
        func.coalesce(counts.c.available_count, 0),
    ).outerjoin(counts, counts.c.book_id == Book.id)


async def get_book_with_counts(session: AsyncSession, library_id: int, book_id: int) -> BookCounts:
    row = (await session.execute(_with_counts(library_id).where(Book.id == book_id))).one_or_none()
    if row is None:
        raise NotFoundError(f"도서를 찾을 수 없습니다: {book_id}")
    return BookCounts(*row)


async def list_books(
    session: AsyncSession,
    library_id: int,
    *,
    limit: int,
    offset: int,
    isbn: str | None = None,
    held: bool = False,
    audience: Audience | None = None,
) -> tuple[list[BookCounts], int]:
    """held=True면 로그인한 기관에 사본이 하나 이상 있는 도서만."""
    query = _with_counts(library_id)
    if isbn is not None:
        query = query.where(Book.isbn == isbn)
    if audience is not None:
        query = query.where(Book.audience == audience)
    if held:
        query = query.where(
            exists().where(
                Holding.book_id == Book.id,
                Holding.library_id == library_id,
                Holding.status != HoldingStatus.WITHDRAWN,
            )
        )
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.execute(query.order_by(Book.title, Book.id).limit(limit).offset(offset))
    return [BookCounts(*row) for row in rows], total or 0


async def update_book(session: AsyncSession, book_id: int, data: BookUpdate) -> Book:
    book = await get_book(session, book_id)
    changes = data.changes()
    if "isbn" in changes:
        new_isbn = changes["isbn"]
        if new_isbn is None and book.isbn is not None:
            has_purchased = await session.scalar(
                select(
                    exists().where(
                        Holding.book_id == book_id,
                        Holding.acquisition_type == AcquisitionType.PURCHASED,
                    )
                )
            )
            if has_purchased:
                raise ConflictError("매입·납품 사본이 있는 도서는 ISBN을 비울 수 없습니다")
        elif new_isbn is not None:
            await _ensure_isbn_free(session, new_isbn, except_id=book_id)
    if "audience" in changes:
        book.audience_source = AudienceSource.MANUAL
    for field, value in changes.items():
        setattr(book, field, value)
    await _commit(session, changes.get("isbn"))
    await session.refresh(book)
    return book


async def delete_book(session: AsyncSession, book_id: int) -> None:
    """어느 기관이든 사본이 있으면 삭제를 거부한다."""
    book = await get_book(session, book_id)
    if await session.scalar(select(exists().where(Holding.book_id == book_id))):
        raise ConflictError("소장 사본이 있는 도서는 삭제할 수 없습니다")
    await session.delete(book)
    await session.commit()
