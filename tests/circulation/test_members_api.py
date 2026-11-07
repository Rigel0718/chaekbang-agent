"""[circulation/members] 회원 REST API와 기관 데이터 분리."""

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


async def test_create_member(admin_client: AsyncClient) -> None:
    """[circulation/members] 회원 등록과 최소 정보 / 정상 등록"""
    res = await admin_client.post("/members", json={"member_number": "M0001", "name": "김이용"})
    assert res.status_code == 201
    body = res.json()
    assert (body["member_number"], body["name"]) == ("M0001", "김이용")
    # 최소 정보: 회원번호와 이름 외의 개인정보 필드가 없다
    assert set(body) == {"id", "member_number", "name", "created_at"}


async def test_missing_name(admin_client: AsyncClient) -> None:
    """[circulation/members] 회원 등록과 최소 정보 / 이름 누락"""
    assert (await admin_client.post("/members", json={"member_number": "M1"})).status_code == 422


async def test_duplicate_number(admin_client: AsyncClient) -> None:
    """[circulation/members] 회원번호 유일성 / 같은 기관에서 중복"""
    await admin_client.post("/members", json={"member_number": "M0001", "name": "김이용"})
    res = await admin_client.post("/members", json={"member_number": "M0001", "name": "박이용"})
    assert res.status_code == 409


async def test_same_number_other_library(
    admin_client: AsyncClient, admin_client_b: AsyncClient
) -> None:
    """[circulation/members] 회원번호 유일성 / 다른 기관의 같은 번호"""
    payload = {"member_number": "M0001", "name": "김이용"}
    assert (await admin_client.post("/members", json=payload)).status_code == 201
    assert (await admin_client_b.post("/members", json=payload)).status_code == 201


async def test_search(admin_client: AsyncClient, session: AsyncSession, library_a: Tenant) -> None:
    """[circulation/members] 회원 조회·수정·삭제 / 이름으로 검색"""
    await add_member(session, library_a.id, "M0001", "김하나")
    await add_member(session, library_a.id, "K-김", "이둘")
    await add_member(session, library_a.id, "M0003", "박셋")
    res = await admin_client.get("/members", params={"q": "김"})
    assert {m["member_number"] for m in res.json()["items"]} == {"M0001", "K-김"}


async def test_get_and_rename(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/members] 회원 조회·수정·삭제 (단건 조회와 이름 수정)"""
    member = await add_member(session, library_a.id, "M0001", "김이용")
    res = await admin_client.patch(f"/members/{member['id']}", json={"name": "김바뀜"})
    assert res.json()["name"] == "김바뀜"
    assert (await admin_client.get(f"/members/{member['id']}")).json()["member_number"] == "M0001"


async def _member_with_loan(session: AsyncSession, library_id: int, *, returned: bool):
    book = await add_library_book(session, library_id)
    holding = await add_holding(session, library_id, book["id"], "A-1")
    member = await add_member(session, library_id, "M0001")
    loan = await add_loan(session, holding, member, returned_on=clock.today() if returned else None)
    return member, loan


async def test_delete_member_with_active_loan(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/members] 회원 조회·수정·삭제 / 대출 중인 회원 삭제"""
    member, loan = await _member_with_loan(session, library_a.id, returned=False)
    assert (await admin_client.delete(f"/members/{member['id']}")).status_code == 409
    assert await fetch(session, "members", member["id"]) is not None
    assert (await fetch(session, "loans", loan["id"]))["member_id"] == member["id"]


async def test_delete_member_with_returned_loans(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/members] 회원 조회·수정·삭제 / 반납 기록만 있는 회원 삭제"""
    member, loan = await _member_with_loan(session, library_a.id, returned=True)
    assert (await admin_client.delete(f"/members/{member['id']}")).status_code == 204
    assert await fetch(session, "members", member["id"]) is None
    kept = await fetch(session, "loans", loan["id"])
    assert kept is not None
    assert kept["member_id"] is None
    assert (kept["holding_id"], kept["loaned_on"]) == (loan["holding_id"], loan["loaned_on"])


async def test_delete_member_without_loans(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/members] 회원 조회·수정·삭제 / 대출 기록 없는 회원 삭제"""
    member = await add_member(session, library_a.id, "M0001")
    assert (await admin_client.delete(f"/members/{member['id']}")).status_code == 204


async def test_active_loan_needs_member_in_db(session: AsyncSession, library_a: Tenant) -> None:
    """[circulation/members] 회원 조회·수정·삭제 / 회원 없는 미반납 대출 직접 저장"""
    book = await add_library_book(session, library_a.id)
    holding = await add_holding(session, library_a.id, book["id"], "A-1")
    today = clock.today()
    await assert_rejected(
        session,
        "loans",
        library_id=library_a.id,
        holding_id=holding["id"],
        member_id=None,
        loaned_on=today,
        due_on=today,
        match="active_has_member",
    )


# --- 기관 데이터 분리 ---


async def test_list_excludes_other_library(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[library/libraries] 기관 데이터 분리 / 목록에 다른 기관 데이터 없음"""
    await add_member(session, library_a.id, "A-1", "에이")
    await add_member(session, library_b.id, "B-1", "비")
    res = await admin_client.get("/members")
    assert [m["member_number"] for m in res.json()["items"]] == ["A-1"]
    assert res.json()["total"] == 1


async def test_body_library_id_ignored(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[library/libraries] 기관 데이터 분리 / 요청 본문의 library_id 무시"""
    res = await admin_client.post(
        "/members", json={"member_number": "M9", "name": "김이용", "library_id": library_b.id}
    )
    assert res.status_code == 201
    assert (await fetch(session, "members", res.json()["id"]))["library_id"] == library_a.id


async def test_update_other_library_member(
    admin_client: AsyncClient, session: AsyncSession, library_b: Tenant
) -> None:
    """[library/libraries] 기관 데이터 분리 / 다른 기관 데이터 수정 (조회·삭제도 404)"""
    theirs = await add_member(session, library_b.id, "B-1", "비")
    url = f"/members/{theirs['id']}"
    assert (await admin_client.patch(url, json={"name": "바뀜"})).status_code == 404
    assert (await admin_client.get(url)).status_code == 404
    assert (await admin_client.delete(url)).status_code == 404
    assert (await fetch(session, "members", theirs["id"]))["name"] == "비"


async def test_kiosk_cannot_list_members(kiosk_client: AsyncClient) -> None:
    """[library/staff-auth] 역할별 접근 제한 / 키오스크의 관리 작업 (GET /members)"""
    assert (await kiosk_client.get("/members")).status_code == 403
    res = await kiosk_client.post("/members", json={"member_number": "M1", "name": "김"})
    assert res.status_code == 403
