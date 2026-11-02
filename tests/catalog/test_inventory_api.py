"""매장 재고 REST API 테스트 (catalog/store-inventory)."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import VALID_ISBN, VALID_ISBN_2, add_book

ITEM = {"isbn": VALID_ISBN, "quantity": 3, "shelf_location": "그림책 A-2"}


async def test_create_inventory(client: AsyncClient, session: AsyncSession) -> None:
    """[catalog/store-inventory] 재고 등록 / 정상 등록"""
    await add_book(session, title="모모", author="미하엘 엔데")
    res = await client.post("/inventory", json=ITEM)
    assert res.status_code == 201
    body = res.json()
    assert (body["quantity"], body["shelf_location"]) == (3, "그림책 A-2")
    assert (body["title"], body["author"]) == ("모모", "미하엘 엔데")


async def test_create_for_unknown_book(client: AsyncClient) -> None:
    """[catalog/store-inventory] 재고 등록 / 도서 목록에 없는 ISBN"""
    res = await client.post("/inventory", json=ITEM)
    assert res.status_code == 404
    assert (await client.get(f"/inventory/{VALID_ISBN}")).status_code == 404


async def test_create_duplicate(client: AsyncClient, session: AsyncSession) -> None:
    """[catalog/store-inventory] 재고 등록 / 이미 재고가 있는 ISBN"""
    await add_book(session)
    await client.post("/inventory", json=ITEM)
    res = await client.post("/inventory", json={**ITEM, "quantity": 5})
    assert res.status_code == 409


async def test_create_negative_quantity(client: AsyncClient, session: AsyncSession) -> None:
    """[catalog/store-inventory] 재고 등록 / 음수 수량"""
    await add_book(session)
    res = await client.post("/inventory", json={**ITEM, "quantity": -1})
    assert res.status_code == 422


async def test_get_inventory(client: AsyncClient, session: AsyncSession) -> None:
    """[catalog/store-inventory] 재고 조회 / 단건 조회"""
    await add_book(session, title="모모", author="미하엘 엔데")
    await client.post("/inventory", json=ITEM)
    res = await client.get("/inventory/978-0-306-40615-7")
    assert res.status_code == 200
    body = res.json()
    assert body["quantity"] == 3
    assert body["shelf_location"] == "그림책 A-2"
    assert (body["title"], body["author"]) == ("모모", "미하엘 엔데")


async def test_get_missing_inventory(client: AsyncClient, session: AsyncSession) -> None:
    """[catalog/store-inventory] 재고 조회 / 재고 없는 ISBN 조회"""
    await add_book(session)
    res = await client.get(f"/inventory/{VALID_ISBN}")
    assert res.status_code == 404


async def test_list_in_stock(client: AsyncClient, session: AsyncSession) -> None:
    """[catalog/store-inventory] 재고 조회 / 품절 제외 목록"""
    await add_book(session, VALID_ISBN)
    await add_book(session, VALID_ISBN_2)
    await client.post("/inventory", json={"isbn": VALID_ISBN, "quantity": 0})
    await client.post("/inventory", json={"isbn": VALID_ISBN_2, "quantity": 2})

    res = await client.get("/inventory", params={"in_stock": "true"})
    assert res.status_code == 200
    body = res.json()
    assert [i["isbn"] for i in body["items"]] == [VALID_ISBN_2]
    assert body["total"] == 1

    all_items = (await client.get("/inventory")).json()
    assert all_items["total"] == 2


async def test_patch_quantity(client: AsyncClient, session: AsyncSession) -> None:
    """[catalog/store-inventory] 재고 수정 / 수량 변경"""
    await add_book(session)
    await client.post("/inventory", json=ITEM)
    res = await client.patch(f"/inventory/{VALID_ISBN}", json={"quantity": 0})
    assert res.status_code == 200
    assert (res.json()["quantity"], res.json()["shelf_location"]) == (0, "그림책 A-2")


async def test_patch_negative_quantity(client: AsyncClient, session: AsyncSession) -> None:
    """[catalog/store-inventory] 재고 수정 / 음수로 수정"""
    await add_book(session)
    await client.post("/inventory", json=ITEM)
    res = await client.patch(f"/inventory/{VALID_ISBN}", json={"quantity": -1})
    assert res.status_code == 422
    assert (await client.get(f"/inventory/{VALID_ISBN}")).json()["quantity"] == 3


async def test_delete_inventory_keeps_book(client: AsyncClient, session: AsyncSession) -> None:
    """[catalog/store-inventory] 재고 삭제 / 재고 삭제"""
    await add_book(session)
    await client.post("/inventory", json=ITEM)
    res = await client.delete(f"/inventory/{VALID_ISBN}")
    assert res.status_code == 204
    assert (await client.get(f"/inventory/{VALID_ISBN}")).status_code == 404
    assert (await client.get(f"/books/{VALID_ISBN}")).status_code == 200
