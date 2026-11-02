"""도서 service. REST 라우터와 이후 에이전트 tool이 함께 쓴다."""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Book, StoreInventory
from app.schemas.catalog import BookCreate, BookUpdate
from app.services.errors import ConflictError, NotFoundError


async def create_book(session: AsyncSession, data: BookCreate) -> Book:
    if await session.get(Book, data.isbn) is not None:
        raise ConflictError(f"이미 등록된 ISBN입니다: {data.isbn}")
    book = Book(**data.model_dump())
    session.add(book)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(f"이미 등록된 ISBN입니다: {data.isbn}") from exc
    await session.refresh(book)
    return book


async def get_book(session: AsyncSession, isbn: str) -> Book:
    book = await session.get(Book, isbn)
    if book is None:
        raise NotFoundError(f"도서를 찾을 수 없습니다: {isbn}")
    return book


async def list_books(session: AsyncSession, *, limit: int, offset: int) -> tuple[list[Book], int]:
    total = await session.scalar(select(func.count()).select_from(Book))
    rows = await session.scalars(
        select(Book).order_by(Book.title, Book.isbn).limit(limit).offset(offset)
    )
    return list(rows), total or 0


async def update_book(session: AsyncSession, isbn: str, data: BookUpdate) -> Book:
    book = await get_book(session, isbn)
    for field, value in data.changes().items():
        setattr(book, field, value)
    await session.commit()
    await session.refresh(book)
    return book


async def delete_book(session: AsyncSession, isbn: str) -> None:
    book = await get_book(session, isbn)
    if await session.get(StoreInventory, isbn) is not None:
        raise ConflictError(f"매장 재고가 등록된 도서는 삭제할 수 없습니다: {isbn}")
    await session.delete(book)
    try:
        await session.commit()
    except IntegrityError as exc:
        # 다른 컨텍스트(추천, 납품 목록 등)의 참조. catalog는 그쪽을 모르므로 DB 제약으로 판단한다.
        await session.rollback()
        raise ConflictError(f"다른 데이터가 참조 중인 도서는 삭제할 수 없습니다: {isbn}") from exc
