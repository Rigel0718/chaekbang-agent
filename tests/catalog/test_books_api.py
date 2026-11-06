"""[catalog/books] 도서 REST API."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Tenant
from tests.helpers import VALID_ISBN, VALID_ISBN_2, add_book, add_holding, make_isbn

BOOK = {"isbn": VALID_ISBN, "title": "모모", "author": "미하엘 엔데", "list_price": 13000}


async def _post(client: AsyncClient, **overrides):
    payload = {**BOOK, **overrides}
    return await client.post("/books", json={k: v for k, v in payload.items() if v is not ...})


# --- 도서 등록 ---


async def test_create_book(admin_client: AsyncClient) -> None:
    """[catalog/books] 도서 등록 / 정상 등록"""
    res = await _post(admin_client, publisher="비룡소", published_date="1999-02-01", kdc="853")
    assert res.status_code == 201
    body = res.json()
    assert isinstance(body["id"], int)
    assert (body["isbn"], body["list_price"], body["kdc"]) == (VALID_ISBN, 13000, "853")


async def test_create_without_isbn(admin_client: AsyncClient) -> None:
    """[catalog/books] 도서 등록 / ISBN 없이 등록"""
    res = await _post(admin_client, isbn=...)
    assert res.status_code == 201
    assert res.json()["isbn"] is None


async def test_create_without_price(admin_client: AsyncClient) -> None:
    """[catalog/books] 도서 등록 / 정가 없이 등록"""
    res = await _post(admin_client, list_price=...)
    assert res.status_code == 201
    assert res.json()["list_price"] is None


async def test_create_missing_title(admin_client: AsyncClient) -> None:
    """[catalog/books] 도서 등록 / 필수 필드 누락"""
    res = await _post(admin_client, title=...)
    assert res.status_code == 422
    assert (await admin_client.get("/books")).json()["total"] == 0


@pytest.mark.parametrize("price", [-1, 13000.5, "13000"])
async def test_create_invalid_price(admin_client: AsyncClient, price) -> None:
    """[catalog/books] 도서 등록 / 정가가 정수가 아님"""
    assert (await _post(admin_client, list_price=price)).status_code == 422


async def test_kiosk_cannot_create(kiosk_client: AsyncClient) -> None:
    """[library/staff-auth] 역할별 접근 제한 / 키오스크의 관리 작업 (POST /books)"""
    assert (await _post(kiosk_client)).status_code == 403
    assert (await kiosk_client.get("/books")).json()["total"] == 0


async def test_kiosk_can_list(kiosk_client: AsyncClient) -> None:
    """[library/staff-auth] 역할별 접근 제한 / 키오스크의 도서 조회"""
    assert (await kiosk_client.get("/books")).status_code == 200


# --- ISBN ---


async def test_create_with_hyphenated_isbn(admin_client: AsyncClient) -> None:
    """[catalog/books] ISBN 형식 정규화와 검증 / 하이픈 포함 입력"""
    res = await _post(admin_client, isbn="978-0-306-40615-7")
    assert res.status_code == 201
    assert res.json()["isbn"] == "9780306406157"


async def test_find_by_hyphenated_isbn(admin_client: AsyncClient) -> None:
    """[catalog/books] ISBN 형식 정규화와 검증 / 하이픈 포함 ISBN으로 조회"""
    created = (await _post(admin_client)).json()
    await _post(admin_client, isbn=VALID_ISBN_2, title="다른 책")
    res = await admin_client.get("/books", params={"isbn": "978-0-306-40615-7"})
    assert res.status_code == 200
    items = res.json()["items"]
    assert [b["id"] for b in items] == [created["id"]]


@pytest.mark.parametrize("isbn", ["0306406152", "97803064061X7"])
async def test_create_wrong_length_or_non_digit(admin_client: AsyncClient, isbn: str) -> None:
    """[catalog/books] ISBN 형식 정규화와 검증 / 자릿수 오류"""
    assert (await _post(admin_client, isbn=isbn)).status_code == 422


async def test_create_wrong_check_digit(admin_client: AsyncClient) -> None:
    """[catalog/books] ISBN 형식 정규화와 검증 / 체크 디지트 오류"""
    assert (await _post(admin_client, isbn="9780306406158")).status_code == 422
    assert (await admin_client.get("/books", params={"isbn": "9780306406158"})).status_code == 422


async def test_create_duplicate(admin_client: AsyncClient) -> None:
    """[catalog/books] ISBN 중복 금지 / 중복 등록"""
    first = (await _post(admin_client)).json()
    res = await _post(admin_client, title="바뀐 제목")
    assert res.status_code == 409
    assert (await admin_client.get(f"/books/{first['id']}")).json()["title"] == "모모"


async def test_many_books_without_isbn(admin_client: AsyncClient) -> None:
    """[catalog/books] ISBN 중복 금지 / ISBN 없는 도서 여러 권"""
    a = await _post(admin_client, isbn=..., title="기증 도서 1")
    b = await _post(admin_client, isbn=..., title="기증 도서 2")
    assert a.status_code == b.status_code == 201
    assert a.json()["id"] != b.json()["id"]


# --- 단건과 목록 조회 ---


async def test_get_book(admin_client: AsyncClient) -> None:
    """[catalog/books] 도서 단건과 목록 조회 / 단건 조회"""
    created = (await _post(admin_client)).json()
    res = await admin_client.get(f"/books/{created['id']}")
    assert res.status_code == 200
    assert res.json()["title"] == "모모"


async def test_get_missing_book(admin_client: AsyncClient) -> None:
    """[catalog/books] 도서 단건과 목록 조회 / 없는 도서 조회"""
    assert (await admin_client.get("/books/999999")).status_code == 404


async def test_list_pagination(admin_client: AsyncClient) -> None:
    """[catalog/books] 도서 단건과 목록 조회 / 목록 페이지네이션 (기본 limit 20 포함)"""
    for n in range(25):
        assert (
            await _post(admin_client, isbn=make_isbn(n), title=f"책 {n:02d}")
        ).status_code == 201
    res = await admin_client.get("/books", params={"limit": 10, "offset": 20})
    body = res.json()
    assert len(body["items"]) == 5
    assert (body["total"], body["limit"], body["offset"]) == (25, 10, 20)
    assert (await admin_client.get("/books")).json()["limit"] == 20


async def test_list_limit_over_max(admin_client: AsyncClient) -> None:
    """[catalog/books] 도서 단건과 목록 조회 / limit 상한 초과"""
    assert (await admin_client.get("/books", params={"limit": 101})).status_code == 422


async def test_filter_unknown_isbn(admin_client: AsyncClient) -> None:
    """[catalog/books] 도서 단건과 목록 조회 / 없는 ISBN으로 거르기"""
    await _post(admin_client)
    res = await admin_client.get("/books", params={"isbn": VALID_ISBN_2})
    assert res.status_code == 200
    assert res.json()["items"] == [] and res.json()["total"] == 0


async def test_counts_per_library(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/books] 도서 단건과 목록 조회 / 기관별 소장 권수"""
    book = await add_book(session)
    await add_holding(session, library_a.id, book["id"], "A-1")
    await add_holding(session, library_a.id, book["id"], "A-2", status="on_loan")
    for n in range(3):
        await add_holding(session, library_b.id, book["id"], f"B-{n}")
    one = (await admin_client.get(f"/books/{book['id']}")).json()
    assert (one["holding_count"], one["available_count"]) == (2, 1)
    listed = (await admin_client.get("/books")).json()["items"][0]
    assert (listed["holding_count"], listed["available_count"]) == (2, 1)


async def test_held_only(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/books] 도서 단건과 목록 조회 / 소장 도서만 거르기"""
    ours = await add_book(session, VALID_ISBN, title="우리 책")
    theirs = await add_book(session, VALID_ISBN_2, title="다른 기관 책")
    await add_book(session, None, title="아무도 없는 책")
    await add_holding(session, library_a.id, ours["id"], "A-1")
    await add_holding(session, library_b.id, theirs["id"], "B-1")
    res = await admin_client.get("/books", params={"held": "true"})
    body = res.json()
    assert [b["id"] for b in body["items"]] == [ours["id"]]
    assert body["total"] == 1
    assert (await admin_client.get("/books")).json()["total"] == 3


# --- 부분 수정 ---


async def test_patch_price_only(admin_client: AsyncClient) -> None:
    """[catalog/books] 도서 부분 수정 / 정가 수정"""
    created = (await _post(admin_client, publisher="비룡소")).json()
    res = await admin_client.patch(f"/books/{created['id']}", json={"list_price": 14000})
    assert res.status_code == 200
    body = res.json()
    assert body["list_price"] == 14000
    assert (body["title"], body["publisher"], body["isbn"]) == ("모모", "비룡소", VALID_ISBN)


async def test_patch_rejects_null_required_field(admin_client: AsyncClient) -> None:
    """[catalog/books] 도서 부분 수정 (필수 필드를 null로 바꿀 수 없음)"""
    created = (await _post(admin_client)).json()
    assert (
        await admin_client.patch(f"/books/{created['id']}", json={"title": None})
    ).status_code == 422


async def test_fill_isbn_later(admin_client: AsyncClient) -> None:
    """[catalog/books] 도서 부분 수정 / ISBN 나중에 채우기"""
    created = (await _post(admin_client, isbn=...)).json()
    res = await admin_client.patch(f"/books/{created['id']}", json={"isbn": "978-0-306-40615-7"})
    assert res.status_code == 200
    assert res.json()["isbn"] == VALID_ISBN


async def test_patch_to_other_books_isbn(admin_client: AsyncClient) -> None:
    """[catalog/books] 도서 부분 수정 / 다른 도서의 ISBN으로 수정"""
    await _post(admin_client)
    other = (await _post(admin_client, isbn=VALID_ISBN_2, title="다른 책")).json()
    res = await admin_client.patch(f"/books/{other['id']}", json={"isbn": VALID_ISBN})
    assert res.status_code == 409
    assert (await admin_client.get(f"/books/{other['id']}")).json()["isbn"] == VALID_ISBN_2


async def test_cannot_clear_isbn_with_purchased_holding(
    admin_client: AsyncClient, session: AsyncSession, library_b: Tenant
) -> None:
    """[catalog/books] 도서 부분 수정 / 매입 사본이 있는 도서의 ISBN 비우기"""
    book = await add_book(session)
    await add_holding(session, library_b.id, book["id"], "B-1")  # 다른 기관의 매입 사본
    res = await admin_client.patch(f"/books/{book['id']}", json={"isbn": None})
    assert res.status_code == 409
    assert (await admin_client.get(f"/books/{book['id']}")).json()["isbn"] == VALID_ISBN


async def test_can_clear_isbn_with_only_donated_holding(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/books] 도서 부분 수정 (기증 사본만 있으면 ISBN을 비울 수 있음)"""
    book = await add_book(session)
    await add_holding(
        session, library_a.id, book["id"], "A-1", acquisition_type="donated", purchase_price=None
    )
    res = await admin_client.patch(f"/books/{book['id']}", json={"isbn": None})
    assert res.status_code == 200
    assert res.json()["isbn"] is None


async def test_patch_missing_book(admin_client: AsyncClient) -> None:
    """[catalog/books] 도서 부분 수정 / 없는 도서 수정"""
    assert (await admin_client.patch("/books/999999", json={"list_price": 1})).status_code == 404


# --- 삭제 ---


async def test_delete_book(admin_client: AsyncClient) -> None:
    """[catalog/books] 소장 사본이 있는 도서의 삭제 금지 / 참조 없는 도서 삭제"""
    created = (await _post(admin_client)).json()
    assert (await admin_client.delete(f"/books/{created['id']}")).status_code == 204
    assert (await admin_client.get(f"/books/{created['id']}")).status_code == 404


async def test_delete_book_with_other_library_holding(
    admin_client: AsyncClient, session: AsyncSession, library_b: Tenant
) -> None:
    """[catalog/books] 소장 사본이 있는 도서의 삭제 금지 / 사본이 있는 도서 삭제"""
    book = await add_book(session)
    await add_holding(session, library_b.id, book["id"], "B-1")
    assert (await admin_client.delete(f"/books/{book['id']}")).status_code == 409
    assert (await admin_client.get(f"/books/{book['id']}")).status_code == 200


# --- 어린이/일반 도서 구분 ---


async def test_audience_default(admin_client: AsyncClient) -> None:
    """[catalog/books] 어린이/일반 도서 구분 / 기본값"""
    body = (await _post(admin_client)).json()
    assert (body["audience"], body["audience_source"]) == ("general", "default")


async def test_audience_manual(admin_client: AsyncClient) -> None:
    """[catalog/books] 어린이/일반 도서 구분 / 관리자 지정 (등록 시 지정 포함)"""
    created = (await _post(admin_client)).json()
    res = await admin_client.patch(f"/books/{created['id']}", json={"audience": "children"})
    assert (res.json()["audience"], res.json()["audience_source"]) == ("children", "manual")

    at_create = (await _post(admin_client, isbn=VALID_ISBN_2, audience="children")).json()
    assert (at_create["audience"], at_create["audience_source"]) == ("children", "manual")


async def test_audience_filter(admin_client: AsyncClient) -> None:
    """[catalog/books] 어린이/일반 도서 구분 / 어린이 도서만 거르기"""
    kid = (await _post(admin_client, audience="children", title="공룡 그림책")).json()
    await _post(admin_client, isbn=VALID_ISBN_2, title="에세이")
    res = await admin_client.get("/books", params={"audience": "children"})
    assert [b["id"] for b in res.json()["items"]] == [kid["id"]]


async def test_withdrawn_is_not_held(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/books] 도서 단건과 목록 조회 / 제적 사본은 소장이 아님"""
    book = await add_book(session)
    await add_holding(session, library_a.id, book["id"], "A-1", status="withdrawn")
    assert (await admin_client.get("/books", params={"held": "true"})).json()["total"] == 0
    body = (await admin_client.get(f"/books/{book['id']}")).json()
    assert (body["holding_count"], body["available_count"]) == (0, 0)


async def test_manual_overrides_import_label(
    admin_client: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/books] 어린이/일반 도서 구분 (근거 우선순위: 관리자 지정이 import_label보다 우선)"""
    book = await add_book(session, audience="children", audience_source="import_label")
    res = await admin_client.patch(f"/books/{book['id']}", json={"audience": "general"})
    assert (res.json()["audience"], res.json()["audience_source"]) == ("general", "manual")
