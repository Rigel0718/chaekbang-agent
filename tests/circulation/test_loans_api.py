"""[circulation/loans] 대출·반납·대출 목록."""

from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from tests.conftest import Tenant
from tests.helpers import (
    add_holding,
    add_library_book,
    add_loan,
    add_member,
    assert_rejected,
    fetch,
)

TODAY = date(2026, 11, 5)


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> date:
    """service가 쓰는 '오늘'을 고정한다."""
    monkeypatch.setattr(clock, "today", lambda: TODAY)
    return TODAY


@pytest.fixture
async def shelf(session: AsyncSession, library_a: Tenant) -> dict:
    """A 기관(자체 대출)의 사본 하나와 회원 하나."""
    book = await add_library_book(session, library_a.id, title="모모")
    holding = await add_holding(session, library_a.id, book["id"], "EM0001")
    member = await add_member(session, library_a.id, "M0001")
    return {"book": book, "holding": holding, "member": member}


async def _borrow(client: AsyncClient, accession: str = "EM0001", member: str = "M0001"):
    return await client.post(
        "/loans", json={"accession_number": accession, "member_number": member}
    )


async def _return(client: AsyncClient, accession: str = "EM0001"):
    return await client.post("/loans/return", json={"accession_number": accession})


# --- 대출하기 ---


async def test_borrow(kiosk_client: AsyncClient, session: AsyncSession, shelf: dict) -> None:
    """[circulation/loans] 대출하기 / 정상 대출 (키오스크 대출 허용)"""
    res = await _borrow(kiosk_client)
    assert res.status_code == 201
    body = res.json()
    assert body["loaned_on"] == TODAY.isoformat()
    assert body["due_on"] == (TODAY + timedelta(days=14)).isoformat()
    assert (body["accession_number"], body["title"], body["member_number"]) == (
        "EM0001",
        "모모",
        "M0001",
    )
    assert body["overdue"] is False
    assert (await fetch(session, "holdings", shelf["holding"]["id"]))["status"] == "on_loan"


async def test_due_date_uses_library_loan_days(
    admin_client: AsyncClient, kiosk_client: AsyncClient, shelf: dict
) -> None:
    """[library/libraries] 기관 정보와 운영 방식 / 기본 대출 기간 수정 (반납 예정일 계산에 쓰임)"""
    await admin_client.patch("/library", json={"default_loan_days": 21})
    body = (await _borrow(kiosk_client)).json()
    assert body["due_on"] == (TODAY + timedelta(days=21)).isoformat()


async def test_unknown_member(
    kiosk_client: AsyncClient, session: AsyncSession, shelf: dict
) -> None:
    """[circulation/loans] 대출하기 / 없는 회원번호"""
    res = await _borrow(kiosk_client, member="NOPE")
    assert res.status_code == 404
    assert (await fetch(session, "holdings", shelf["holding"]["id"]))["status"] == "available"


async def test_other_library_accession(
    kiosk_client: AsyncClient, session: AsyncSession, shelf: dict, library_b: Tenant
) -> None:
    """[circulation/loans] 대출하기 / 다른 기관의 등록번호"""
    book = await add_library_book(session, library_b.id, None, title="B 기관 책")
    await add_holding(
        session, library_b.id, book["id"], "B-ONLY", acquisition_type="donated", purchase_price=None
    )
    assert (await _borrow(kiosk_client, accession="B-ONLY")).status_code == 404


# --- 대출 가능 조건 ---


async def test_already_on_loan(kiosk_client: AsyncClient, shelf: dict) -> None:
    """[circulation/loans] 대출 가능 조건 / 대출 중인 사본"""
    assert (await _borrow(kiosk_client)).status_code == 201
    assert (await _borrow(kiosk_client)).status_code == 409


async def test_lost_copy(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/loans] 대출 가능 조건 / 분실된 사본"""
    book = await add_library_book(session, library_a.id)
    await add_holding(session, library_a.id, book["id"], "LOST-1", status="lost")
    await add_member(session, library_a.id, "M0001")
    assert (await _borrow(kiosk_client, accession="LOST-1")).status_code == 409


async def test_two_active_loans_rejected_by_db(
    session: AsyncSession, shelf: dict, library_a: Tenant
) -> None:
    """[circulation/loans] 대출 가능 조건 / 반납 안 된 대출 두 건 직접 저장"""
    await add_loan(session, shelf["holding"], shelf["member"], loaned_on=TODAY)
    await assert_rejected(
        session,
        "loans",
        library_id=library_a.id,
        holding_id=shelf["holding"]["id"],
        member_id=shelf["member"]["id"],
        loaned_on=TODAY,
        due_on=TODAY,
        match="uq_loans_active_holding",
    )


# --- 운영 방식 ---


async def _imported_shelf(session: AsyncSession, library_b: Tenant) -> None:
    book = await add_library_book(session, library_b.id)
    await add_holding(session, library_b.id, book["id"], "EM0001")
    await add_member(session, library_b.id, "M0001")


async def test_imported_library_borrow(
    kiosk_client_b: AsyncClient, session: AsyncSession, library_b: Tenant
) -> None:
    """[circulation/loans] 운영 방식에 따른 대출 차단 / 가져오기 기관에서 대출"""
    await _imported_shelf(session, library_b)
    res = await _borrow(kiosk_client_b)
    assert res.status_code == 409
    assert "데스크" in res.json()["detail"]
    assert (await kiosk_client_b.get("/holdings")).json()["items"][0]["status"] == "available"


async def test_imported_library_return(
    kiosk_client_b: AsyncClient, session: AsyncSession, library_b: Tenant
) -> None:
    """[circulation/loans] 운영 방식에 따른 대출 차단 / 가져오기 기관에서 반납"""
    await _imported_shelf(session, library_b)
    res = await _return(kiosk_client_b)
    assert res.status_code == 409
    assert "데스크" in res.json()["detail"]


# --- 반납 ---


async def test_kiosk_return(kiosk_client: AsyncClient, session: AsyncSession, shelf: dict) -> None:
    """[circulation/loans] 반납 / 키오스크에서 반납"""
    await _borrow(kiosk_client)
    res = await _return(kiosk_client)
    assert res.status_code == 200
    assert res.json()["returned_on"] == TODAY.isoformat()
    assert (await fetch(session, "holdings", shelf["holding"]["id"]))["status"] == "available"
    # 반납한 책은 다시 빌릴 수 있다
    assert (await _borrow(kiosk_client)).status_code == 201


async def test_admin_return(
    admin_client: AsyncClient, kiosk_client: AsyncClient, shelf: dict
) -> None:
    """[circulation/loans] 반납 (관리자도 같은 엔드포인트로 반납)"""
    await _borrow(kiosk_client)
    assert (await _return(admin_client)).status_code == 200


async def test_return_not_on_loan(kiosk_client: AsyncClient, shelf: dict) -> None:
    """[circulation/loans] 반납 / 대출 중이 아닌 사본 반납 (대출된 적 없음, 이미 반납됨)"""
    assert (await _return(kiosk_client)).status_code == 409
    await _borrow(kiosk_client)
    assert (await _return(kiosk_client)).status_code == 200
    assert (await _return(kiosk_client)).status_code == 409


async def test_return_other_library_accession(
    kiosk_client: AsyncClient, session: AsyncSession, shelf: dict, library_b: Tenant
) -> None:
    """[circulation/loans] 반납 / 다른 기관의 등록번호로 반납"""
    book = await add_library_book(session, library_b.id, None, title="B 기관 책")
    theirs = await add_holding(
        session, library_b.id, book["id"], "B-ONLY", acquisition_type="donated", purchase_price=None
    )
    loan = await add_loan(session, theirs, await add_member(session, library_b.id, "B-M1"))
    assert (await _return(kiosk_client, accession="B-ONLY")).status_code == 404
    assert (await fetch(session, "loans", loan["id"]))["returned_on"] is None


# --- 대출 목록과 연체 ---


async def _history(session: AsyncSession, library_a: Tenant) -> dict:
    """연체 1건, 대출 중(기한 남음) 1건, 반납 1건."""
    book = await add_library_book(session, library_a.id)
    member = await add_member(session, library_a.id, "M0001")
    h = [await add_holding(session, library_a.id, book["id"], f"H-{n}") for n in range(3)]
    overdue = await add_loan(
        session,
        h[0],
        member,
        loaned_on=TODAY - timedelta(days=20),
        due_on=TODAY - timedelta(days=6),
    )
    active = await add_loan(
        session, h[1], member, loaned_on=TODAY, due_on=TODAY + timedelta(days=14)
    )
    returned = await add_loan(
        session,
        h[2],
        member,
        loaned_on=TODAY - timedelta(days=30),
        due_on=TODAY - timedelta(days=16),
        returned_on=TODAY - timedelta(days=20),
    )
    return {"overdue": overdue, "active": active, "returned": returned}


async def test_overdue_list(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/loans] 대출 목록과 연체 / 연체 목록"""
    loans = await _history(session, library_a)
    res = await admin_client.get("/loans", params={"status": "overdue"})
    items = res.json()["items"]
    assert [i["id"] for i in items] == [loans["overdue"]["id"]]
    assert items[0]["overdue"] is True


async def test_active_excludes_returned(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/loans] 대출 목록과 연체 / 반납된 대출 제외"""
    loans = await _history(session, library_a)
    res = await admin_client.get("/loans", params={"status": "active"})
    assert {i["id"] for i in res.json()["items"]} == {loans["overdue"]["id"], loans["active"]["id"]}
    returned = (await admin_client.get("/loans", params={"status": "returned"})).json()["items"]
    assert [i["id"] for i in returned] == [loans["returned"]["id"]]
    assert (await admin_client.get("/loans")).json()["total"] == 3


async def test_list_after_member_deleted(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/loans] 대출 목록과 연체 (회원이 삭제된 반납 기록은 회원번호가 비어 있음)"""
    book = await add_library_book(session, library_a.id)
    holding = await add_holding(session, library_a.id, book["id"], "H-1")
    member = await add_member(session, library_a.id, "M0001")
    await add_loan(session, holding, member, returned_on=TODAY)
    assert (await admin_client.delete(f"/members/{member['id']}")).status_code == 204
    items = (await admin_client.get("/loans")).json()["items"]
    assert items[0]["member_number"] is None


async def test_list_only_own_library(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[library/libraries] 기관 데이터 분리 (대출 목록에 다른 기관 대출 없음)"""
    book = await add_library_book(session, library_b.id)
    theirs = await add_holding(session, library_b.id, book["id"], "B-1")
    await add_loan(session, theirs, await add_member(session, library_b.id, "B-M1"))
    assert (await admin_client.get("/loans")).json()["total"] == 0


async def test_kiosk_cannot_list_loans(kiosk_client: AsyncClient) -> None:
    """[library/staff-auth] 역할별 접근 제한 (대출 목록 조회는 관리자만)"""
    assert (await kiosk_client.get("/loans")).status_code == 403
