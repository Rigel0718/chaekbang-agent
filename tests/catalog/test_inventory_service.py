"""매장 재고 service 단위 테스트 (catalog/store-inventory)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.catalog import InventoryCreate, InventoryUpdate
from app.services.catalog import inventory
from app.services.errors import ConflictError, NotFoundError
from tests.helpers import VALID_ISBN, VALID_ISBN_2, add_book


async def test_create_includes_book_title_and_author(session: AsyncSession) -> None:
    """[catalog/store-inventory] 재고 등록 / 정상 등록"""
    await add_book(session, title="모모", author="미하엘 엔데")
    item = await inventory.create_inventory(
        session, InventoryCreate(isbn=VALID_ISBN, quantity=3, shelf_location="그림책 A-2")
    )
    assert (item.quantity, item.shelf_location) == (3, "그림책 A-2")
    assert (item.title, item.author) == ("모모", "미하엘 엔데")


async def test_create_for_unknown_book(session: AsyncSession) -> None:
    """[catalog/store-inventory] 재고 등록 / 도서 목록에 없는 ISBN"""
    with pytest.raises(NotFoundError):
        await inventory.create_inventory(session, InventoryCreate(isbn=VALID_ISBN, quantity=1))


async def test_create_duplicate(session: AsyncSession) -> None:
    """[catalog/store-inventory] 재고 등록 / 이미 재고가 있는 ISBN"""
    await add_book(session)
    await inventory.create_inventory(session, InventoryCreate(isbn=VALID_ISBN, quantity=1))
    with pytest.raises(ConflictError):
        await inventory.create_inventory(session, InventoryCreate(isbn=VALID_ISBN, quantity=2))


async def test_list_in_stock_only(session: AsyncSession) -> None:
    """[catalog/store-inventory] 재고 조회 / 품절 제외 목록"""
    await add_book(session, VALID_ISBN)
    await add_book(session, VALID_ISBN_2)
    await inventory.create_inventory(session, InventoryCreate(isbn=VALID_ISBN, quantity=0))
    await inventory.create_inventory(session, InventoryCreate(isbn=VALID_ISBN_2, quantity=2))
    items, total = await inventory.list_inventory(session, limit=20, offset=0, in_stock=True)
    assert total == 1
    assert [i.isbn for i in items] == [VALID_ISBN_2]


async def test_update_and_delete(session: AsyncSession) -> None:
    """[catalog/store-inventory] 재고 수정 / 수량 변경, 재고 삭제 / 재고 삭제"""
    await add_book(session)
    await inventory.create_inventory(
        session, InventoryCreate(isbn=VALID_ISBN, quantity=3, shelf_location="A-1")
    )
    item = await inventory.update_inventory(session, VALID_ISBN, InventoryUpdate(quantity=0))
    assert (item.quantity, item.shelf_location) == (0, "A-1")
    await inventory.delete_inventory(session, VALID_ISBN)
    with pytest.raises(NotFoundError):
        await inventory.get_inventory(session, VALID_ISBN)
