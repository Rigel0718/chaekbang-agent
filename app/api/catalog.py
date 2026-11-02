from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.matching.isbn import InvalidIsbnError, normalize_isbn
from app.schemas.catalog import (
    BookCreate,
    BookRead,
    BookUpdate,
    InventoryCreate,
    InventoryRead,
    InventoryUpdate,
)
from app.schemas.common import Page, Pagination
from app.services.catalog import books, inventory

router = APIRouter(tags=["catalog"])

Session = Annotated[AsyncSession, Depends(get_session)]


def path_isbn(isbn: str) -> str:
    """경로의 ISBN도 본문과 같은 규칙으로 정규화한다."""
    try:
        return normalize_isbn(isbn)
    except InvalidIsbnError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


PathIsbn = Annotated[str, Depends(path_isbn)]


@router.post("/books", status_code=status.HTTP_201_CREATED, response_model=BookRead)
async def create_book(data: BookCreate, session: Session):
    return await books.create_book(session, data)


@router.get("/books", response_model=Page[BookRead])
async def list_books(session: Session, page: Annotated[Pagination, Query()]):
    items, total = await books.list_books(session, limit=page.limit, offset=page.offset)
    return Page[BookRead](
        items=[BookRead.model_validate(b) for b in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/books/{isbn}", response_model=BookRead)
async def get_book(isbn: PathIsbn, session: Session):
    return await books.get_book(session, isbn)


@router.patch("/books/{isbn}", response_model=BookRead)
async def update_book(isbn: PathIsbn, data: BookUpdate, session: Session):
    return await books.update_book(session, isbn, data)


@router.delete("/books/{isbn}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_book(isbn: PathIsbn, session: Session) -> None:
    await books.delete_book(session, isbn)


@router.post("/inventory", status_code=status.HTTP_201_CREATED, response_model=InventoryRead)
async def create_inventory(data: InventoryCreate, session: Session):
    return await inventory.create_inventory(session, data)


@router.get("/inventory", response_model=Page[InventoryRead])
async def list_inventory(
    session: Session,
    page: Annotated[Pagination, Query()],
    in_stock: Annotated[bool, Query(description="true면 수량 1 이상만")] = False,
):
    items, total = await inventory.list_inventory(
        session, limit=page.limit, offset=page.offset, in_stock=in_stock
    )
    return Page[InventoryRead](
        items=[InventoryRead.model_validate(i) for i in items],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.get("/inventory/{isbn}", response_model=InventoryRead)
async def get_inventory(isbn: PathIsbn, session: Session):
    return await inventory.get_inventory(session, isbn)


@router.patch("/inventory/{isbn}", response_model=InventoryRead)
async def update_inventory(isbn: PathIsbn, data: InventoryUpdate, session: Session):
    return await inventory.update_inventory(session, isbn, data)


@router.delete("/inventory/{isbn}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inventory(isbn: PathIsbn, session: Session) -> None:
    await inventory.delete_inventory(session, isbn)
