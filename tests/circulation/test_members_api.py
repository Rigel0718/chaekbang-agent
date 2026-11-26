"""[circulation/members] 회원 REST API와 기관 데이터 분리."""

from httpx import AsyncClient
from sqlalchemy import text
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
    insert,
)


async def test_create_member(admin_client: AsyncClient) -> None:
    """[circulation/members] 회원 등록과 최소 정보 / 정상 등록"""
    res = await admin_client.post(
        "/members", json={"member_number": "M0001", "name": "김이용", "phone": "01012345678"}
    )
    assert res.status_code == 201
    body = res.json()
    assert (body["member_number"], body["name"]) == ("M0001", "김이용")
    # 최소 정보: 회원번호, 이름, 전화번호 외의 개인정보 필드가 없다
    assert set(body) == {"id", "member_number", "name", "phone", "created_at"}
    assert body["phone"] == "01012345678"


async def test_missing_phone(admin_client: AsyncClient) -> None:
    """[circulation/members] 회원 등록과 최소 정보 / 전화번호 누락"""
    bodies = [{"member_number": "M1", "name": "김이용"}]
    bodies += [{"member_number": "M1", "name": "김이용", "phone": v} for v in ("", " ", None)]
    for body in bodies:
        res = await admin_client.post("/members", json=body)
        assert res.status_code == 422, body
    assert (await admin_client.get("/members")).json()["total"] == 0


async def test_missing_name(admin_client: AsyncClient) -> None:
    """[circulation/members] 회원 등록과 최소 정보 / 이름 누락"""
    assert (await admin_client.post("/members", json={"member_number": "M1"})).status_code == 422


async def test_duplicate_number(admin_client: AsyncClient) -> None:
    """[circulation/members] 회원번호 유일성 / 같은 기관에서 중복"""
    first = {"member_number": "M0001", "name": "김이용", "phone": "01011112222"}
    assert (await admin_client.post("/members", json=first)).status_code == 201
    second = {"member_number": "M0001", "name": "박이용", "phone": "01033334444"}
    res = await admin_client.post("/members", json=second)
    assert res.status_code == 409


async def test_same_number_other_library(
    admin_client: AsyncClient, admin_client_b: AsyncClient
) -> None:
    """[circulation/members] 회원번호 유일성 / 다른 기관의 같은 번호"""
    payload = {"member_number": "M0001", "name": "김이용", "phone": "01012345678"}
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


async def test_delete_member_with_book_requests(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/members] 회원 조회·수정·삭제 / 희망도서 신청이 있는 회원 삭제"""
    member = await add_member(session, library_a.id, "M0001")
    other = await add_member(session, library_a.id, "M0002")
    values = {"library_id": library_a.id, "title_key": "작별하지않는다"}
    open_request = await insert(
        session, "book_requests", member_id=member["id"], title="작별하지 않는다", **values
    )
    closed = await insert(
        session,
        "book_requests",
        member_id=member["id"],
        title="소년이 온다",
        title_key="소년이온다",
        status="closed",
        library_id=library_a.id,
    )
    others = await insert(
        session, "book_requests", member_id=other["id"], title="작별하지 않는다", **values
    )
    assert (await admin_client.delete(f"/members/{member['id']}")).status_code == 204
    assert await fetch(session, "members", member["id"]) is None
    for row in (open_request, closed):
        kept = await fetch(session, "book_requests", row["id"])
        assert kept is not None and kept["member_id"] is None
        assert kept["title"] == row["title"] and kept["created_at"] == row["created_at"]
    assert (await fetch(session, "book_requests", others["id"]))["member_id"] == other["id"]
    listed = (await admin_client.get("/book-requests")).json()["items"]
    by_id = {r["id"]: r["member_number"] for r in listed}
    assert by_id == {open_request["id"]: None, closed["id"]: None, others["id"]: "M0002"}


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
        "/members",
        json={
            "member_number": "M9",
            "name": "김이용",
            "phone": "01012345678",
            "library_id": library_b.id,
        },
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


async def test_create_member_with_phone(admin_client: AsyncClient) -> None:
    """[circulation/members] 회원 등록과 최소 정보 / 전화번호와 함께 등록"""
    res = await admin_client.post(
        "/members", json={"member_number": "M0002", "name": "김이용", "phone": "010-1234-5678"}
    )
    assert res.status_code == 201
    assert res.json()["phone"] == "01012345678"
    spaced = await admin_client.post(
        "/members", json={"member_number": "M0003", "name": "박이용", "phone": "02 123.4567"}
    )
    assert spaced.json()["phone"] == "021234567"


async def test_phone_format_rejected(admin_client: AsyncClient) -> None:
    """[circulation/members] 회원 등록과 최소 정보 / 전화번호 형식 오류"""
    for index, phone in enumerate(["1234", "010-1234-56789", "01012", "abc", "(02)123-4567"]):
        res = await admin_client.post(
            "/members", json={"member_number": f"X{index}", "name": "김이용", "phone": phone}
        )
        assert res.status_code == 422, phone
    assert (await admin_client.get("/members")).json()["total"] == 0


async def test_search_ignores_phone(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/members] 회원 조회·수정·삭제 / 전화번호로는 찾지 않음"""
    await admin_client.post(
        "/members", json={"member_number": "M0001", "name": "김하나", "phone": "01012345678"}
    )
    res = await admin_client.get("/members", params={"q": "5678"})
    assert res.json()["items"] == []
    assert res.json()["total"] == 0


async def test_update_and_clear_phone(admin_client: AsyncClient) -> None:
    """[circulation/members] 회원 조회·수정·삭제 / 전화번호 지우기"""
    member = (
        await admin_client.post(
            "/members", json={"member_number": "M0001", "name": "김하나", "phone": "01012345678"}
        )
    ).json()
    changed = await admin_client.patch(f"/members/{member['id']}", json={"phone": "010-9999-0000"})
    assert changed.json()["phone"] == "01099990000"
    for value in (None, "", " "):
        cleared = await admin_client.patch(f"/members/{member['id']}", json={"phone": value})
        assert cleared.status_code == 422, value
    untouched = await admin_client.patch(f"/members/{member['id']}", json={"name": "김둘"})
    assert untouched.json()["phone"] == "01099990000"
    bad = await admin_client.patch(f"/members/{member['id']}", json={"phone": "12"})
    assert bad.status_code == 422
    assert (await admin_client.get(f"/members/{member['id']}")).json()["phone"] == "01099990000"


async def test_rename_existing_member_without_phone(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/members] 회원 조회·수정·삭제 / 번호 없는 기존 회원의 이름 고치기"""
    member = await add_member(session, library_a.id, "M0001", "김옛날")  # 규칙 전에 번호 없이 등록
    res = await admin_client.patch(f"/members/{member['id']}", json={"name": "김바뀜"})
    assert res.status_code == 200
    assert (res.json()["name"], res.json()["phone"]) == ("김바뀜", None)
    added = await admin_client.patch(f"/members/{member['id']}", json={"phone": "010-5555-6666"})
    assert added.json()["phone"] == "01055556666"


async def test_kiosk_cannot_create_member_with_phone(kiosk_client: AsyncClient) -> None:
    """[circulation/members] 회원 등록과 최소 정보 / 전화번호는 관리자 API에서만"""
    res = await kiosk_client.post(
        "/members", json={"member_number": "M1", "name": "김이용", "phone": "01012345678"}
    )
    assert res.status_code == 403


# --- 전화번호 유일성 ---


async def _create(client: AsyncClient, number: str, phone: str | None = None):
    body = {"member_number": number, "name": "이용자"}
    if phone is not None:
        body["phone"] = phone
    return await client.post("/members", json=body)


async def test_duplicate_phone_create(admin_client: AsyncClient) -> None:
    """[circulation/members] 전화번호 유일성 / 같은 기관에서 번호 중복 등록, 형식만 다른 번호"""
    assert (await _create(admin_client, "M0001", "01012345678")).status_code == 201
    for phone in ("01012345678", "010-1234-5678"):
        res = await _create(admin_client, "M0002", phone)
        assert res.status_code == 409
        assert "01012345678" not in res.text and "5678" not in res.text
    assert len((await admin_client.get("/members")).json()["items"]) == 1


async def test_duplicate_phone_update(admin_client: AsyncClient) -> None:
    """[circulation/members] 전화번호 유일성 / 번호 수정이 겹침, 자기 번호로 다시 고치기는 허용"""
    first = (await _create(admin_client, "M0001", "01012345678")).json()
    second = (await _create(admin_client, "M0002", "01022223333")).json()
    res = await admin_client.patch(f"/members/{second['id']}", json={"phone": "010-1234-5678"})
    assert res.status_code == 409
    assert (await admin_client.get(f"/members/{second['id']}")).json()["phone"] == "01022223333"
    same = await admin_client.patch(f"/members/{first['id']}", json={"phone": "010-1234-5678"})
    assert same.status_code == 200


async def test_same_phone_other_library(
    admin_client: AsyncClient, admin_client_b: AsyncClient
) -> None:
    """[circulation/members] 전화번호 유일성 / 다른 기관의 같은 번호"""
    assert (await _create(admin_client, "M0001", "01012345678")).status_code == 201
    assert (await _create(admin_client_b, "M0001", "01012345678")).status_code == 201


async def test_many_members_without_phone(session: AsyncSession, library_a: Tenant) -> None:
    """[circulation/members] 전화번호 유일성 / 번호 없는 회원 여럿 (직접 저장)"""
    for number in ("M0001", "M0002", "M0003"):
        await add_member(session, library_a.id, number)
    count = await session.scalar(
        text("select count(*) from members where library_id = :id and phone is null"),
        {"id": library_a.id},
    )
    assert count == 3
