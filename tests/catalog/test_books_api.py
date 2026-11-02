"""도서 REST API 테스트 (catalog/books)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.matching.isbn import isbn13_check_digit
from tests.helpers import VALID_ISBN, insert

BOOK = {"isbn": VALID_ISBN, "title": "모모", "author": "미하엘 엔데", "list_price": 13000}


def _isbn(n: int) -> str:
    first12 = f"979110000{n:03d}"
    return first12 + isbn13_check_digit(first12)


async def _post(client: AsyncClient, **overrides):
    return await client.post("/books", json={**BOOK, **overrides})


async def test_create_book(client: AsyncClient) -> None:
    """[catalog/books] 도서 등록 / 정상 등록"""
    res = await _post(client, publisher="비룡소", published_date="1999-02-01")
    assert res.status_code == 201
    body = res.json()
    assert body["isbn"] == VALID_ISBN
    assert body["list_price"] == 13000
    assert body["publisher"] == "비룡소"


async def test_create_missing_title(client: AsyncClient) -> None:
    """[catalog/books] 도서 등록 / 필수 필드 누락"""
    payload = {k: v for k, v in BOOK.items() if k != "title"}
    res = await client.post("/books", json=payload)
    assert res.status_code == 422
    assert (await client.get(f"/books/{VALID_ISBN}")).status_code == 404


@pytest.mark.parametrize("price", [-1, 13000.5, "13000"])
async def test_create_invalid_price(client: AsyncClient, price) -> None:
    """[catalog/books] 도서 등록 / 정가가 정수가 아님"""
    res = await _post(client, list_price=price)
    assert res.status_code == 422


async def test_create_with_hyphenated_isbn(client: AsyncClient) -> None:
    """[catalog/books] ISBN 형식 정규화와 검증 / 하이픈 포함 입력"""
    res = await _post(client, isbn="978-0-306-40615-7")
    assert res.status_code == 201
    assert res.json()["isbn"] == "9780306406157"


async def test_get_with_hyphenated_isbn(client: AsyncClient) -> None:
    """[catalog/books] ISBN 형식 정규화와 검증 / 하이픈 포함 ISBN으로 조회"""
    await _post(client)
    res = await client.get("/books/978-0-306-40615-7")
    assert res.status_code == 200
    assert res.json()["isbn"] == VALID_ISBN


@pytest.mark.parametrize("isbn", ["0306406152", "97803064061X7"])
async def test_create_wrong_length_or_non_digit(client: AsyncClient, isbn: str) -> None:
    """[catalog/books] ISBN 형식 정규화와 검증 / 자릿수 오류"""
    res = await _post(client, isbn=isbn)
    assert res.status_code == 422


async def test_create_wrong_check_digit(client: AsyncClient) -> None:
    """[catalog/books] ISBN 형식 정규화와 검증 / 체크 디지트 오류"""
    res = await _post(client, isbn="9780306406158")
    assert res.status_code == 422


async def test_create_duplicate(client: AsyncClient) -> None:
    """[catalog/books] ISBN 중복 금지 / 중복 등록"""
    await _post(client)
    res = await _post(client, title="바뀐 제목")
    assert res.status_code == 409
    assert (await client.get(f"/books/{VALID_ISBN}")).json()["title"] == "모모"


async def test_get_book(client: AsyncClient) -> None:
    """[catalog/books] 도서 조회 / 단건 조회"""
    await _post(client)
    res = await client.get(f"/books/{VALID_ISBN}")
    assert res.status_code == 200
    assert res.json()["title"] == "모모"


async def test_get_missing_book(client: AsyncClient) -> None:
    """[catalog/books] 도서 조회 / 없는 도서 조회"""
    res = await client.get(f"/books/{VALID_ISBN}")
    assert res.status_code == 404


async def test_list_pagination(client: AsyncClient) -> None:
    """[catalog/books] 도서 조회 / 목록 페이지네이션"""
    for n in range(25):
        assert (await _post(client, isbn=_isbn(n), title=f"책 {n:02d}")).status_code == 201
    res = await client.get("/books", params={"limit": 10, "offset": 20})
    assert res.status_code == 200
    body = res.json()
    assert len(body["items"]) == 5
    assert body["total"] == 25
    assert (body["limit"], body["offset"]) == (10, 20)


async def test_list_default_limit(client: AsyncClient) -> None:
    """[catalog/books] 도서 조회 (기본 limit 20)"""
    res = await client.get("/books")
    assert res.json()["limit"] == 20


async def test_list_limit_over_max(client: AsyncClient) -> None:
    """[catalog/books] 도서 조회 / limit 상한 초과"""
    res = await client.get("/books", params={"limit": 101})
    assert res.status_code == 422


async def test_patch_price_only(client: AsyncClient) -> None:
    """[catalog/books] 도서 수정 / 정가 수정"""
    await _post(client, publisher="비룡소")
    res = await client.patch(f"/books/{VALID_ISBN}", json={"list_price": 14000})
    assert res.status_code == 200
    body = res.json()
    assert body["list_price"] == 14000
    assert (body["title"], body["publisher"]) == ("모모", "비룡소")


async def test_patch_rejects_null_required_field(client: AsyncClient) -> None:
    """[catalog/books] 도서 수정 (필수 필드를 null로 바꿀 수 없음)"""
    await _post(client)
    res = await client.patch(f"/books/{VALID_ISBN}", json={"title": None})
    assert res.status_code == 422


async def test_patch_missing_book(client: AsyncClient) -> None:
    """[catalog/books] 도서 수정 / 없는 도서 수정"""
    res = await client.patch(f"/books/{VALID_ISBN}", json={"list_price": 14000})
    assert res.status_code == 404


async def test_delete_book(client: AsyncClient) -> None:
    """[catalog/books] 도서 삭제 / 참조 없는 도서 삭제"""
    await _post(client)
    res = await client.delete(f"/books/{VALID_ISBN}")
    assert res.status_code == 204
    assert (await client.get(f"/books/{VALID_ISBN}")).status_code == 404


async def test_delete_book_with_inventory(client: AsyncClient, session: AsyncSession) -> None:
    """[catalog/books] 도서 삭제 / 재고가 있는 도서 삭제"""
    await _post(client)
    await insert(session, "store_inventory", isbn=VALID_ISBN, quantity=2)
    res = await client.delete(f"/books/{VALID_ISBN}")
    assert res.status_code == 409
    assert (await client.get(f"/books/{VALID_ISBN}")).status_code == 200


@pytest.mark.parametrize(
    ("table", "values"),
    [
        ("curations", {"kind": "today_pick", "title": "t", "body": "b", "isbn": VALID_ISBN}),
        ("book_requests", {"title": "모모", "contact": "010", "isbn": VALID_ISBN}),
    ],
)
async def test_delete_book_referenced_by_other_context(
    client: AsyncClient, session: AsyncSession, table: str, values: dict
) -> None:
    """[catalog/books] 도서 삭제 / 다른 컨텍스트가 참조하는 도서 삭제"""
    await _post(client)
    await insert(session, table, **values)
    res = await client.delete(f"/books/{VALID_ISBN}")
    assert res.status_code == 409
    assert (await client.get(f"/books/{VALID_ISBN}")).status_code == 200


async def test_delete_book_referenced_by_order_item(
    client: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/books] 도서 삭제 / 다른 컨텍스트가 참조하는 도서 삭제 (납품 목록 행)"""
    await _post(client)
    institution = await insert(session, "institutions", name="학교", type="school")
    order = await insert(
        session, "institution_orders", institution_id=institution["id"], source_filename="a.xlsx"
    )
    await insert(
        session,
        "order_items",
        order_id=order["id"],
        row_no=1,
        raw_title="모모",
        quantity=1,
        matched_isbn=VALID_ISBN,
    )
    res = await client.delete(f"/books/{VALID_ISBN}")
    assert res.status_code == 409
