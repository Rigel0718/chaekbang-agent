"""[circulation/book-requests] 희망도서 신청, 회원 확인, 중복·소장 검사, 목록·닫기, 기관 분리."""

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Tenant
from tests.helpers import (
    VALID_ISBN,
    VALID_ISBN_2,
    add_book,
    add_holding,
    add_library_book,
    add_member,
)

CANARY = "ZQ-CANARY-7731"
TITLE = "작별하지 않는다"


@pytest.fixture
async def member(session: AsyncSession, library_a: Tenant) -> dict:
    return await add_member(session, library_a.id, "M0001")


def _body(member_number: str = "M0001", **overrides) -> dict:
    return {"member_number": member_number, "title": TITLE, "author": "한강", **overrides}


async def _rows(session: AsyncSession, library_id: int) -> list:
    result = await session.execute(
        text("SELECT * FROM book_requests WHERE library_id = :id ORDER BY id"), {"id": library_id}
    )
    return list(result.mappings())


# --- 희망도서 신청 ---


async def test_request_book(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant, member: dict
) -> None:
    """[circulation/book-requests] 희망도서 신청 / 정상 신청"""
    res = await kiosk_client.post("/book-requests", json=_body())
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "requested"
    assert body["title"] == TITLE and body["author"] == "한강" and body["isbn"] is None
    (row,) = await _rows(session, library_a.id)
    assert row["member_id"] == member["id"] and row["status"] == "requested"


async def test_admin_can_request(admin_client: AsyncClient, member: dict) -> None:
    """[circulation/book-requests] 희망도서 신청 / 정상 신청 (관리자도 신청할 수 있다)"""
    assert (await admin_client.post("/book-requests", json=_body())).status_code == 201


async def test_isbn_normalized(kiosk_client: AsyncClient, member: dict) -> None:
    """[circulation/book-requests] 희망도서 신청 / ISBN 정규화"""
    res = await kiosk_client.post("/book-requests", json=_body(isbn="978-89-364-3412-0"))
    assert res.status_code == 201
    assert res.json()["isbn"] == "9788936434120"


async def test_blank_optional_values_are_null(kiosk_client: AsyncClient, member: dict) -> None:
    """[circulation/book-requests] 희망도서 신청 / ISBN 정규화 (빈 저자·ISBN은 없음)"""
    res = await kiosk_client.post("/book-requests", json=_body(author="  ", isbn=""))
    assert res.status_code == 201
    assert res.json()["author"] is None and res.json()["isbn"] is None


@pytest.mark.parametrize("isbn", ["9788936434121", "89-364-3412-6", "12345"])
async def test_invalid_isbn(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant, member: dict, isbn: str
) -> None:
    """[circulation/book-requests] 희망도서 신청 / 잘못된 ISBN"""
    res = await kiosk_client.post("/book-requests", json=_body(isbn=isbn))
    assert res.status_code == 422
    assert await _rows(session, library_a.id) == []


@pytest.mark.parametrize("title", [None, "", "   ", "가" * 201, "!!!"])
async def test_invalid_title(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant, member: dict, title
) -> None:
    """[circulation/book-requests] 희망도서 신청 / 서명 누락 (길이 초과, 글자 없는 서명 포함)"""
    body = _body()
    if title is None:
        del body["title"]
    else:
        body["title"] = title
    assert (await kiosk_client.post("/book-requests", json=body)).status_code == 422
    assert await _rows(session, library_a.id) == []


async def test_author_too_long(kiosk_client: AsyncClient, member: dict) -> None:
    """[circulation/book-requests] 희망도서 신청 / 서명 누락 (저자 100자 초과)"""
    assert (
        await kiosk_client.post("/book-requests", json=_body(author="가" * 101))
    ).status_code == 422


async def test_external_library_can_request(
    kiosk_client_b: AsyncClient, session: AsyncSession, library_b: Tenant
) -> None:
    """[circulation/book-requests] 희망도서 신청 / 외부 대출 기관의 신청"""
    await add_member(session, library_b.id, "B0001")
    res = await kiosk_client_b.post("/book-requests", json=_body("B0001"))
    assert res.status_code == 201


async def test_request_needs_token(client: AsyncClient) -> None:
    """[circulation/book-requests] 희망도서 신청 / 정상 신청 (토큰 없이는 401)"""
    assert (await client.post("/book-requests", json=_body())).status_code == 401


# --- 신청 회원 확인 ---


async def test_unknown_member(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/book-requests] 신청 회원 확인 / 없는 회원번호"""
    res = await kiosk_client.post("/book-requests", json=_body(CANARY))
    assert res.status_code == 404
    assert CANARY not in res.text
    assert await _rows(session, library_a.id) == []


async def test_member_of_other_library(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[circulation/book-requests] 신청 회원 확인 / 다른 기관의 회원번호"""
    await add_member(session, library_b.id, "B0001")
    res = await kiosk_client.post("/book-requests", json=_body("B0001"))
    assert res.status_code == 404
    assert await _rows(session, library_a.id) == []


# --- 같은 회원의 중복 신청 ---


async def test_duplicate_same_member(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant, member: dict
) -> None:
    """[circulation/book-requests] 같은 회원의 중복 신청 / 같은 회원의 같은 서명"""
    assert (await kiosk_client.post("/book-requests", json=_body())).status_code == 201
    res = await kiosk_client.post("/book-requests", json=_body(title="작별 하지 않는다!"))
    assert res.status_code == 409
    assert len(await _rows(session, library_a.id)) == 1


async def test_duplicate_other_member(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant, member: dict
) -> None:
    """[circulation/book-requests] 같은 회원의 중복 신청 / 다른 회원의 같은 서명"""
    await add_member(session, library_a.id, "M0002")
    assert (await kiosk_client.post("/book-requests", json=_body("M0001"))).status_code == 201
    assert (await kiosk_client.post("/book-requests", json=_body("M0002"))).status_code == 201
    assert len(await _rows(session, library_a.id)) == 2


async def test_request_again_after_closed(
    kiosk_client: AsyncClient, admin_client: AsyncClient, member: dict
) -> None:
    """[circulation/book-requests] 같은 회원의 중복 신청 / 닫힌 신청 뒤 다시 신청"""
    first = (await kiosk_client.post("/book-requests", json=_body())).json()
    closed = await admin_client.patch(f"/book-requests/{first['id']}", json={"status": "closed"})
    assert closed.status_code == 200
    assert (await kiosk_client.post("/book-requests", json=_body())).status_code == 201


# --- 소장 도서 신청 거부 ---


async def test_held_isbn_rejected(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant, member: dict
) -> None:
    """[circulation/book-requests] 소장 도서 신청 거부 / 소장한 ISBN (기관 도서의 ISBN)"""
    book = await add_library_book(session, library_a.id, VALID_ISBN, title="모모")
    await add_holding(session, library_a.id, book["id"], "EM0001")
    res = await kiosk_client.post("/book-requests", json=_body(isbn=VALID_ISBN))
    assert res.status_code == 409
    assert len(await _rows(session, library_a.id)) == 0


async def test_held_official_isbn_rejected(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant, member: dict
) -> None:
    """[circulation/book-requests] 소장 도서 신청 거부 / 소장한 ISBN (공식 서지로 연결된 책)"""
    official = await add_book(session, VALID_ISBN_2)
    linked = await add_library_book(
        session, library_a.id, None, title="연결된 책", book_id=official["id"]
    )
    await add_holding(session, library_a.id, linked["id"], "EM0002", status="on_loan")
    res = await kiosk_client.post("/book-requests", json=_body(isbn=VALID_ISBN_2))
    assert res.status_code == 409


async def test_isbn_held_only_by_other_library(
    kiosk_client: AsyncClient, session: AsyncSession, library_b: Tenant, member: dict
) -> None:
    """[circulation/book-requests] 소장 도서 신청 거부 / 다른 기관만 소장한 ISBN"""
    book = await add_library_book(session, library_b.id, VALID_ISBN, title="모모")
    await add_holding(session, library_b.id, book["id"], "EM0001")
    assert (
        await kiosk_client.post("/book-requests", json=_body(isbn=VALID_ISBN))
    ).status_code == 201


async def test_withdrawn_only_book_can_be_requested(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant, member: dict
) -> None:
    """[circulation/book-requests] 소장 도서 신청 거부 / 소장한 ISBN (제적 사본뿐이면 소장 아님)"""
    book = await add_library_book(session, library_a.id, VALID_ISBN, title="모모")
    await add_holding(session, library_a.id, book["id"], "EM0001", status="withdrawn")
    assert (
        await kiosk_client.post("/book-requests", json=_body(isbn=VALID_ISBN))
    ).status_code == 201


async def test_same_title_without_isbn_not_checked(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant, member: dict
) -> None:
    """[circulation/book-requests] 소장 도서 신청 거부 / 서명만 같은 신청"""
    book = await add_library_book(session, library_a.id, VALID_ISBN, title=TITLE)
    await add_holding(session, library_a.id, book["id"], "EM0001")
    assert (await kiosk_client.post("/book-requests", json=_body())).status_code == 201


# --- 신청 응답 ---


async def test_response_has_no_member_values(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/book-requests] 신청 응답 / 신청 응답의 회원 값"""
    await add_member(session, library_a.id, CANARY, name="회원이름")
    res = await kiosk_client.post("/book-requests", json=_body(CANARY))
    assert res.status_code == 201
    assert set(res.json()) == {"id", "title", "author", "isbn", "status", "created_at"}
    assert CANARY not in res.text and "회원이름" not in res.text


# --- 목록과 닫기 ---


async def test_list_filter_and_order(
    kiosk_client: AsyncClient, admin_client: AsyncClient, member: dict
) -> None:
    """[circulation/book-requests] 희망도서 목록과 닫기 / 상태로 거르기"""
    ids = []
    for title in ("첫째 책", "둘째 책", "셋째 책"):
        res = await kiosk_client.post("/book-requests", json=_body(title=title))
        ids.append(res.json()["id"])
    await admin_client.patch(f"/book-requests/{ids[0]}", json={"status": "closed"})
    res = await admin_client.get("/book-requests", params={"status": "requested"})
    assert res.status_code == 200
    body = res.json()
    assert [r["id"] for r in body["items"]] == [ids[2], ids[1]]
    assert body["total"] == 2
    assert all(r["member_number"] == "M0001" and r["status"] == "requested" for r in body["items"])
    everything = await admin_client.get("/book-requests")
    assert everything.json()["total"] == 3
    closed = (await admin_client.get("/book-requests", params={"status": "closed"})).json()
    assert [r["id"] for r in closed["items"]] == [ids[0]]


async def test_list_paginates(
    kiosk_client: AsyncClient, admin_client: AsyncClient, member: dict
) -> None:
    """[circulation/book-requests] 희망도서 목록과 닫기 / 상태로 거르기 (페이지)"""
    for title in ("가책", "나책", "다책"):
        await kiosk_client.post("/book-requests", json=_body(title=title))
    page = (await admin_client.get("/book-requests", params={"limit": 2, "offset": 2})).json()
    assert page["total"] == 3 and len(page["items"]) == 1


async def test_close(admin_client: AsyncClient, kiosk_client: AsyncClient, member: dict) -> None:
    """[circulation/book-requests] 희망도서 목록과 닫기 / 닫기"""
    created = (await kiosk_client.post("/book-requests", json=_body())).json()
    res = await admin_client.patch(f"/book-requests/{created['id']}", json={"status": "closed"})
    assert res.status_code == 200
    assert res.json()["status"] == "closed" and res.json()["closed_at"] is not None
    again = await admin_client.patch(f"/book-requests/{created['id']}", json={"status": "closed"})
    assert again.status_code == 200
    assert again.json()["closed_at"] == res.json()["closed_at"]


@pytest.mark.parametrize("status", ["requested", "ordered", None])
async def test_close_rejects_other_status(
    admin_client: AsyncClient, kiosk_client: AsyncClient, member: dict, status
) -> None:
    """[circulation/book-requests] 희망도서 목록과 닫기 / 되돌리기 거부"""
    created = (await kiosk_client.post("/book-requests", json=_body())).json()
    body = {} if status is None else {"status": status}
    res = await admin_client.patch(f"/book-requests/{created['id']}", json=body)
    assert res.status_code == 422
    still = (await admin_client.get("/book-requests")).json()["items"][0]
    assert still["status"] == "requested"


async def test_kiosk_cannot_list_or_close(
    kiosk_client: AsyncClient, admin_client: AsyncClient, member: dict
) -> None:
    """[circulation/book-requests] 희망도서 목록과 닫기 / 키오스크의 목록과 닫기"""
    created = (await kiosk_client.post("/book-requests", json=_body())).json()
    assert (await kiosk_client.get("/book-requests")).status_code == 403
    res = await kiosk_client.patch(f"/book-requests/{created['id']}", json={"status": "closed"})
    assert res.status_code == 403
    assert (await admin_client.get("/book-requests")).json()["items"][0]["status"] == "requested"


# --- 기관 분리 ---


async def test_list_only_own_library(
    kiosk_client: AsyncClient,
    admin_client: AsyncClient,
    kiosk_client_b: AsyncClient,
    admin_client_b: AsyncClient,
    session: AsyncSession,
    library_a: Tenant,
    library_b: Tenant,
) -> None:
    """[circulation/book-requests] 희망도서의 기관 분리 / 다른 기관의 목록"""
    await add_member(session, library_a.id, "M0001")
    await add_member(session, library_b.id, "B0001")
    await kiosk_client.post("/book-requests", json=_body("M0001", title="A의 책"))
    await kiosk_client_b.post("/book-requests", json=_body("B0001", title="B의 책"))
    a = (await admin_client.get("/book-requests")).json()
    b = (await admin_client_b.get("/book-requests")).json()
    assert [r["title"] for r in a["items"]] == ["A의 책"] and a["total"] == 1
    assert [r["title"] for r in b["items"]] == ["B의 책"] and b["total"] == 1


async def test_close_other_library_request(
    admin_client: AsyncClient,
    kiosk_client_b: AsyncClient,
    admin_client_b: AsyncClient,
    session: AsyncSession,
    library_b: Tenant,
) -> None:
    """[circulation/book-requests] 희망도서의 기관 분리 / 다른 기관의 신청 닫기"""
    await add_member(session, library_b.id, "B0001")
    created = (await kiosk_client_b.post("/book-requests", json=_body("B0001"))).json()
    res = await admin_client.patch(f"/book-requests/{created['id']}", json={"status": "closed"})
    assert res.status_code == 404
    assert (await admin_client_b.get("/book-requests")).json()["items"][0]["status"] == "requested"
