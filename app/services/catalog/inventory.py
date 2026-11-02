"""매장 재고 service. 추천·검색이 매장 재고를 먼저 볼 때 이 함수를 쓴다."""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Book, StoreInventory
from app.schemas.catalog import InventoryCreate, InventoryUpdate
from app.services.errors import ConflictError, NotFoundError


async def create_inventory(session: AsyncSession, data: InventoryCreate) -> StoreInventory:
    if await session.get(Book, data.isbn) is None:
        raise NotFoundError(f"도서 목록에 없는 ISBN입니다: {data.isbn}")
    if await session.get(StoreInventory, data.isbn) is not None:
        raise ConflictError(f"이미 재고가 등록된 ISBN입니다: {data.isbn}")
    item = StoreInventory(**data.model_dump())
    session.add(item)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(f"이미 재고가 등록된 ISBN입니다: {data.isbn}") from exc
    await session.refresh(item)
    return item


async def get_inventory(session: AsyncSession, isbn: str) -> StoreInventory:
    item = await session.get(StoreInventory, isbn)
    if item is None:
        raise NotFoundError(f"재고가 없습니다: {isbn}")
    return item


async def list_inventory(
    session: AsyncSession, *, limit: int, offset: int, in_stock: bool = False
) -> tuple[list[StoreInventory], int]:
    query = select(StoreInventory)
    if in_stock:
        query = query.where(StoreInventory.quantity > 0)
    total = await session.scalar(select(func.count()).select_from(query.subquery()))
    rows = await session.scalars(
        query.order_by(StoreInventory.shelf_location.nulls_last(), StoreInventory.isbn)
        .limit(limit)
        .offset(offset)
    )
    return list(rows), total or 0


async def update_inventory(
    session: AsyncSession, isbn: str, data: InventoryUpdate
) -> StoreInventory:
    item = await get_inventory(session, isbn)
    for field, value in data.changes().items():
        setattr(item, field, value)
    await session.commit()
    await session.refresh(item)
    return item


async def delete_inventory(session: AsyncSession, isbn: str) -> None:
    item = await get_inventory(session, isbn)
    await session.delete(item)
    await session.commit()
