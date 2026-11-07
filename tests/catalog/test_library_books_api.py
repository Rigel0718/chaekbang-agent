"""[catalog/library-books] 도서 REST API."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Tenant
from tests.helpers import (
    VALID_ISBN,
    VALID_ISBN_2,
    add_book,
    add_holding,
    add_library_book,
    fetch,
    make_isbn,
)

BOOK = {"isbn": VALID_ISBN, "title": "모모", "author": "미하엘 엔데", "list_price": 13000}


async def _post(client: AsyncClient, **overrides):
    payload = {**BOOK, **overrides}
    return await client.post(
        "/library-books", json={k: v for k, v in payload.items() if v is not ...}
    )


# --- 도서 등록 ---


async def test_create_book(admin_client: AsyncClient) -> None:
    """[catalog/library-books] 기관 도서 등록 / 정상 등록"""
    res = await _post(admin_client, publisher="비룡소", published_date="1999-02-01", kdc="853")
    assert res.status_code == 201
    body = res.json()
    assert isinstance(body["id"], int)
    assert (body["isbn"], body["list_price"], body["kdc"]) == (VALID_ISBN, 13000, "853")


async def test_create_without_isbn(admin_client: AsyncClient) -> None:
    """[catalog/library-books] 기관 도서 등록 / ISBN 없이 등록"""
    res = await _post(admin_client, isbn=...)
    assert res.status_code == 201
    assert res.json()["isbn"] is None


async def test_create_without_price(admin_client: AsyncClient) -> None:
    """[catalog/library-books] 기관 도서 등록 / 정가 없이 등록"""
    res = await _post(admin_client, list_price=...)
    assert res.status_code == 201
    assert res.json()["list_price"] is None


async def test_create_missing_title(admin_client: AsyncClient) -> None:
    """[catalog/library-books] 기관 도서 등록 / 필수 필드 누락"""
    res = await _post(admin_client, title=...)
    assert res.status_code == 422
    assert (await admin_client.get("/library-books")).json()["total"] == 0


@pytest.mark.parametrize("price", [-1, 13000.5, "13000"])
async def test_create_invalid_price(admin_client: AsyncClient, price) -> None:
    """[catalog/library-books] 기관 도서 등록 / 정가가 정수가 아님"""
    assert (await _post(admin_client, list_price=price)).status_code == 422


async def test_kiosk_cannot_create(kiosk_client: AsyncClient) -> None:
    """[library/staff-auth] 역할별 접근 제한 / 키오스크의 관리 작업 (POST /library-books)"""
    assert (await _post(kiosk_client)).status_code == 403
    assert (await kiosk_client.get("/library-books")).json()["total"] == 0


async def test_kiosk_can_list(kiosk_client: AsyncClient) -> None:
    """[library/staff-auth] 역할별 접근 제한 / 키오스크의 도서 조회"""
    assert (await kiosk_client.get("/library-books")).status_code == 200


# --- ISBN ---


async def test_create_with_hyphenated_isbn(admin_client: AsyncClient) -> None:
    """[catalog/library-books] ISBN 형식 정규화와 검증 / 하이픈 포함 입력"""
    res = await _post(admin_client, isbn="978-0-306-40615-7")
    assert res.status_code == 201
    assert res.json()["isbn"] == "9780306406157"


async def test_find_by_hyphenated_isbn(admin_client: AsyncClient) -> None:
    """[catalog/library-books] ISBN 형식 정규화와 검증 / 하이픈 포함 ISBN으로 조회"""
    created = (await _post(admin_client)).json()
    await _post(admin_client, isbn=VALID_ISBN_2, title="다른 책")
    res = await admin_client.get("/library-books", params={"isbn": "978-0-306-40615-7"})
    assert res.status_code == 200
    items = res.json()["items"]
    assert [b["id"] for b in items] == [created["id"]]


@pytest.mark.parametrize("isbn", ["0306406152", "97803064061X7"])
async def test_create_wrong_length_or_non_digit(admin_client: AsyncClient, isbn: str) -> None:
    """[catalog/library-books] ISBN 형식 정규화와 검증 / 자릿수 오류"""
    assert (await _post(admin_client, isbn=isbn)).status_code == 422


async def test_create_wrong_check_digit(admin_client: AsyncClient) -> None:
    """[catalog/library-books] ISBN 형식 정규화와 검증 / 체크 디지트 오류"""
    assert (await _post(admin_client, isbn="9780306406158")).status_code == 422
    assert (
        await admin_client.get("/library-books", params={"isbn": "9780306406158"})
    ).status_code == 422


async def test_create_duplicate(admin_client: AsyncClient) -> None:
    """[catalog/library-books] ISBN 중복 금지 / 중복 등록"""
    first = (await _post(admin_client)).json()
    res = await _post(admin_client, title="바뀐 제목")
    assert res.status_code == 409
    assert (await admin_client.get(f"/library-books/{first['id']}")).json()["title"] == "모모"


async def test_same_isbn_in_other_library(
    admin_client: AsyncClient, admin_client_b: AsyncClient
) -> None:
    """[catalog/library-books] ISBN 중복 금지 / 다른 기관의 같은 ISBN"""
    ours = await _post(admin_client)
    theirs = await _post(admin_client_b)
    assert ours.status_code == theirs.status_code == 201
    assert ours.json()["id"] != theirs.json()["id"]


async def test_many_books_without_isbn(admin_client: AsyncClient) -> None:
    """[catalog/library-books] ISBN 중복 금지 / ISBN 없는 도서 여러 권"""
    a = await _post(admin_client, isbn=..., title="기증 도서 1")
    b = await _post(admin_client, isbn=..., title="기증 도서 2")
    assert a.status_code == b.status_code == 201
    assert a.json()["id"] != b.json()["id"]


# --- 단건과 목록 조회 ---


async def test_get_book(admin_client: AsyncClient) -> None:
    """[catalog/library-books] 기관 도서 단건과 목록 조회 / 단건 조회"""
    created = (await _post(admin_client)).json()
    res = await admin_client.get(f"/library-books/{created['id']}")
    assert res.status_code == 200
    assert res.json()["title"] == "모모"


async def test_get_missing_book(admin_client: AsyncClient) -> None:
    """[catalog/library-books] 기관 도서 단건과 목록 조회 / 없는 도서 조회"""
    assert (await admin_client.get("/library-books/999999")).status_code == 404


async def test_list_pagination(admin_client: AsyncClient) -> None:
    """[catalog/library-books] 기관 도서 단건과 목록 조회 / 목록 페이지네이션 (기본 limit 포함)"""
    for n in range(25):
        assert (
            await _post(admin_client, isbn=make_isbn(n), title=f"책 {n:02d}")
        ).status_code == 201
    res = await admin_client.get("/library-books", params={"limit": 10, "offset": 20})
    body = res.json()
    assert len(body["items"]) == 5
    assert (body["total"], body["limit"], body["offset"]) == (25, 10, 20)
    assert (await admin_client.get("/library-books")).json()["limit"] == 20


async def test_list_limit_over_max(admin_client: AsyncClient) -> None:
    """[catalog/library-books] 기관 도서 단건과 목록 조회 / limit 상한 초과"""
    assert (await admin_client.get("/library-books", params={"limit": 101})).status_code == 422


async def test_filter_unknown_isbn(admin_client: AsyncClient) -> None:
    """[catalog/library-books] 기관 도서 단건과 목록 조회 / 없는 ISBN으로 거르기"""
    await _post(admin_client)
    res = await admin_client.get("/library-books", params={"isbn": VALID_ISBN_2})
    assert res.status_code == 200
    assert res.json()["items"] == [] and res.json()["total"] == 0


async def test_get_other_library_book(
    admin_client: AsyncClient, session: AsyncSession, library_b: Tenant
) -> None:
    """[catalog/library-books] 기관 도서 단건과 목록 조회 / 다른 기관 도서 조회"""
    theirs = await add_library_book(session, library_b.id)
    assert (await admin_client.get(f"/library-books/{theirs['id']}")).status_code == 404


async def test_list_excludes_other_library(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/library-books] 기관 도서 단건과 목록 조회 / 목록에 다른 기관 도서 없음"""
    ours = await add_library_book(session, library_a.id)
    await add_library_book(session, library_b.id)
    body = (await admin_client.get("/library-books")).json()
    assert [b["id"] for b in body["items"]] == [ours["id"]]
    assert body["total"] == 1


async def test_counts(admin_client: AsyncClient, session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/library-books] 기관 도서 단건과 목록 조회 / 소장 권수"""
    book = await add_library_book(session, library_a.id)
    await add_holding(session, library_a.id, book["id"], "A-1")
    await add_holding(session, library_a.id, book["id"], "A-2", status="on_loan")
    one = (await admin_client.get(f"/library-books/{book['id']}")).json()
    assert (one["holding_count"], one["available_count"]) == (2, 1)
    listed = (await admin_client.get("/library-books")).json()["items"][0]
    assert (listed["holding_count"], listed["available_count"]) == (2, 1)


async def test_held_only(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/library-books] 기관 도서 단건과 목록 조회 / 소장 도서만 거르기"""
    held = await add_library_book(session, library_a.id, VALID_ISBN, title="소장 책")
    await add_library_book(session, library_a.id, None, title="사본 없는 책")
    await add_holding(session, library_a.id, held["id"], "A-1")
    res = await admin_client.get("/library-books", params={"held": "true"})
    body = res.json()
    assert [b["id"] for b in body["items"]] == [held["id"]]
    assert body["total"] == 1
    assert (await admin_client.get("/library-books")).json()["total"] == 2


# --- 공식 서지 연결 ---


async def test_links_official_book(admin_client: AsyncClient, session: AsyncSession) -> None:
    """[catalog/library-books] 공식 서지 연결 / 공식 서지가 있는 ISBN"""
    official = await add_book(session)
    body = (await _post(admin_client)).json()
    assert body["book_id"] == official["id"]


async def test_no_official_book(admin_client: AsyncClient) -> None:
    """[catalog/library-books] 공식 서지 연결 / 공식 서지가 없는 ISBN"""
    res = await _post(admin_client, title="기관 서명")
    body = (await admin_client.get(f"/library-books/{res.json()['id']}")).json()
    assert body["book_id"] is None
    assert body["title"] == "기관 서명"


async def test_no_isbn_has_no_link(admin_client: AsyncClient) -> None:
    """[catalog/library-books] 공식 서지 연결 / ISBN 없는 도서"""
    assert (await _post(admin_client, isbn=...)).json()["book_id"] is None


# --- 표시 값 ---


async def test_official_value_first(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/library-books] 표시 값 / 공식 값 우선"""
    official = await add_book(session, title="클린 코드")
    book = await add_library_book(session, library_a.id, title="클린코드", book_id=official["id"])
    one = (await admin_client.get(f"/library-books/{book['id']}")).json()
    assert one["title"] == "클린 코드"
    listed = (await admin_client.get("/library-books")).json()["items"][0]
    assert listed["title"] == "클린 코드"


async def test_empty_official_field_uses_library_value(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/library-books] 표시 값 / 공식 값이 빈 필드"""
    official = await add_book(session, publisher=None)
    book = await add_library_book(
        session, library_a.id, publisher="기관 출판사", book_id=official["id"]
    )
    body = (await admin_client.get(f"/library-books/{book['id']}")).json()
    assert body["publisher"] == "기관 출판사"


async def test_holding_shows_official_title(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/library-books] 표시 값 / 사본 응답의 서명"""
    official = await add_book(session, title="클린 코드")
    book = await add_library_book(session, library_a.id, title="클린코드", book_id=official["id"])
    holding = await add_holding(session, library_a.id, book["id"], "A-1")
    assert (await admin_client.get(f"/holdings/{holding['id']}")).json()["title"] == "클린 코드"


# --- 부분 수정 ---


async def test_patch_price_only(admin_client: AsyncClient) -> None:
    """[catalog/library-books] 기관 도서 부분 수정 / 정가 수정"""
    created = (await _post(admin_client, publisher="비룡소")).json()
    res = await admin_client.patch(f"/library-books/{created['id']}", json={"list_price": 14000})
    assert res.status_code == 200
    body = res.json()
    assert body["list_price"] == 14000
    assert (body["title"], body["publisher"], body["isbn"]) == ("모모", "비룡소", VALID_ISBN)


async def test_patch_rejects_null_required_field(admin_client: AsyncClient) -> None:
    """[catalog/library-books] 기관 도서 부분 수정 (필수 필드를 null로 바꿀 수 없음)"""
    created = (await _post(admin_client)).json()
    assert (
        await admin_client.patch(f"/library-books/{created['id']}", json={"title": None})
    ).status_code == 422


async def test_fill_isbn_later(admin_client: AsyncClient) -> None:
    """[catalog/library-books] 기관 도서 부분 수정 / ISBN 나중에 채우기"""
    created = (await _post(admin_client, isbn=...)).json()
    res = await admin_client.patch(
        f"/library-books/{created['id']}", json={"isbn": "978-0-306-40615-7"}
    )
    assert res.status_code == 200
    assert res.json()["isbn"] == VALID_ISBN


async def test_patch_to_other_books_isbn(admin_client: AsyncClient) -> None:
    """[catalog/library-books] 기관 도서 부분 수정 / 다른 도서의 ISBN으로 수정"""
    await _post(admin_client)
    other = (await _post(admin_client, isbn=VALID_ISBN_2, title="다른 책")).json()
    res = await admin_client.patch(f"/library-books/{other['id']}", json={"isbn": VALID_ISBN})
    assert res.status_code == 409
    assert (await admin_client.get(f"/library-books/{other['id']}")).json()["isbn"] == VALID_ISBN_2


async def test_cannot_clear_isbn_with_purchased_holding(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/library-books] 기관 도서 부분 수정 / 매입 사본이 있는 도서의 ISBN 비우기"""
    book = await add_library_book(session, library_a.id)
    await add_holding(session, library_a.id, book["id"], "A-1")
    res = await admin_client.patch(f"/library-books/{book['id']}", json={"isbn": None})
    assert res.status_code == 409
    assert (await admin_client.get(f"/library-books/{book['id']}")).json()["isbn"] == VALID_ISBN


async def test_linked_book_rejects_bibliographic_patch(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/library-books] 기관 도서 부분 수정 / 연결된 도서의 서지 수정"""
    official = await add_book(session, title="공식 서명")
    book = await add_library_book(session, library_a.id, title="기관 서명", book_id=official["id"])
    res = await admin_client.patch(f"/library-books/{book['id']}", json={"title": "바꾼 서명"})
    assert res.status_code == 409
    assert (await admin_client.get(f"/library-books/{book['id']}")).json()["title"] == "공식 서명"
    allowed = await admin_client.patch(f"/library-books/{book['id']}", json={"isbn": VALID_ISBN_2})
    assert allowed.status_code == 200


async def test_filling_isbn_links_official(
    admin_client: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/library-books] 기관 도서 부분 수정 / ISBN 나중에 채우기 (공식 서지 연결)"""
    official = await add_book(session)
    created = (await _post(admin_client, isbn=...)).json()
    res = await admin_client.patch(f"/library-books/{created['id']}", json={"isbn": VALID_ISBN})
    assert res.json()["book_id"] == official["id"]


async def test_fixing_wrong_isbn_clears_link(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/library-books] 기관 도서 부분 수정 / 잘못 연결된 ISBN 고치기"""
    official = await add_book(session, title="공식 서명")
    book = await add_library_book(session, library_a.id, title="기관 서명", book_id=official["id"])
    res = await admin_client.patch(f"/library-books/{book['id']}", json={"isbn": VALID_ISBN_2})
    body = res.json()
    assert (body["isbn"], body["book_id"], body["title"]) == (VALID_ISBN_2, None, "기관 서명")


async def test_patch_other_library_book(
    admin_client: AsyncClient, session: AsyncSession, library_b: Tenant
) -> None:
    """[catalog/library-books] 기관 도서 부분 수정 / 다른 기관 도서 수정"""
    theirs = await add_library_book(session, library_b.id, title="B 서명")
    res = await admin_client.patch(f"/library-books/{theirs['id']}", json={"title": "바꿈"})
    assert res.status_code == 404
    assert (await fetch(session, "library_books", theirs["id"]))["title"] == "B 서명"


async def test_can_clear_isbn_with_only_donated_holding(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/library-books] 기관 도서 부분 수정 (기증 사본만 있으면 ISBN을 비울 수 있음)"""
    book = await add_library_book(session, library_a.id)
    await add_holding(
        session, library_a.id, book["id"], "A-1", acquisition_type="donated", purchase_price=None
    )
    res = await admin_client.patch(f"/library-books/{book['id']}", json={"isbn": None})
    assert res.status_code == 200
    assert res.json()["isbn"] is None


async def test_patch_missing_book(admin_client: AsyncClient) -> None:
    """[catalog/library-books] 기관 도서 부분 수정 / 없는 도서 수정"""
    assert (
        await admin_client.patch("/library-books/999999", json={"list_price": 1})
    ).status_code == 404


# --- 삭제 ---


async def test_delete_book(admin_client: AsyncClient) -> None:
    """[catalog/library-books] 소장 사본이 있는 도서의 삭제 금지 / 참조 없는 도서 삭제"""
    created = (await _post(admin_client)).json()
    assert (await admin_client.delete(f"/library-books/{created['id']}")).status_code == 204
    assert (await admin_client.get(f"/library-books/{created['id']}")).status_code == 404


async def test_delete_book_with_holding(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/library-books] 소장 사본이 있는 도서의 삭제 금지 / 사본이 있는 도서 삭제"""
    book = await add_library_book(session, library_a.id)
    await add_holding(session, library_a.id, book["id"], "A-1", status="withdrawn")
    assert (await admin_client.delete(f"/library-books/{book['id']}")).status_code == 409
    assert (await admin_client.get(f"/library-books/{book['id']}")).status_code == 200


async def test_delete_other_library_book(
    admin_client: AsyncClient, session: AsyncSession, library_b: Tenant
) -> None:
    """[catalog/library-books] 소장 사본이 있는 도서의 삭제 금지 / 다른 기관 도서 삭제"""
    theirs = await add_library_book(session, library_b.id)
    assert (await admin_client.delete(f"/library-books/{theirs['id']}")).status_code == 404
    assert await fetch(session, "library_books", theirs["id"]) is not None


async def test_delete_keeps_official_book(admin_client: AsyncClient, session: AsyncSession) -> None:
    """[catalog/library-books] 소장 사본이 있는 도서의 삭제 금지 (공식 서지는 함께 지워지지 않음)"""
    official = await add_book(session)
    created = (await _post(admin_client)).json()
    assert (await admin_client.delete(f"/library-books/{created['id']}")).status_code == 204
    assert await fetch(session, "books", official["id"]) is not None


async def test_withdrawn_is_not_held(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/library-books] 기관 도서 단건과 목록 조회 / 제적 사본은 소장이 아님"""
    book = await add_library_book(session, library_a.id)
    await add_holding(session, library_a.id, book["id"], "A-1", status="withdrawn")
    assert (await admin_client.get("/library-books", params={"held": "true"})).json()["total"] == 0
    body = (await admin_client.get(f"/library-books/{book['id']}")).json()
    assert (body["holding_count"], body["available_count"]) == (0, 0)


# --- 처리 상태 ---


async def test_linked_book_is_enriched(admin_client: AsyncClient, session: AsyncSession) -> None:
    """[catalog/library-books] 공식 서지 연결 / 연결되면 처리 완료"""
    await add_book(session)
    assert (await _post(admin_client)).json()["enrichment_status"] == "enriched"


async def test_unlinked_book_is_pending(admin_client: AsyncClient) -> None:
    """[catalog/library-books] 공식 서지 연결 / 연결이 없으면 처리 대기"""
    assert (await _post(admin_client)).json()["enrichment_status"] == "pending"


async def test_isbn_change_returns_to_pending(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/library-books] 공식 서지 연결 / ISBN 수정 시 다시 대기"""
    book = await add_library_book(session, library_a.id, enrichment_status="not_found")
    res = await admin_client.patch(f"/library-books/{book['id']}", json={"isbn": VALID_ISBN_2})
    assert res.json()["enrichment_status"] == "pending"


async def test_same_isbn_keeps_status(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/library-books] 공식 서지 연결 (같은 ISBN을 다시 보내면 상태를 바꾸지 않음)"""
    book = await add_library_book(session, library_a.id, enrichment_status="not_found")
    res = await admin_client.patch(f"/library-books/{book['id']}", json={"isbn": VALID_ISBN})
    assert res.json()["enrichment_status"] == "not_found"
