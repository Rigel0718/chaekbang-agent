"""[circulation/member-login] 휴대폰 번호 로그인, 회원 세션, 로그아웃, 기관 분리.

회원 세션이 필요한 요청은 희망도서 신청(`POST /book-requests`)으로 확인한다.
"""

import logging
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from tests.conftest import Tenant, make_client
from tests.helpers import add_member, add_staff_session, login_member

PHONE = "01012345678"
UNKNOWN = "01099998888"
REQUIRED = "회원 로그인을 해 주세요."
HEADER = "X-Member-Token"


@pytest.fixture
async def member(session: AsyncSession, library_a: Tenant) -> dict:
    return await add_member(session, library_a.id, "M0001", name="김비밀", phone=PHONE)


async def _login(client: AsyncClient, phone: str = PHONE):
    return await client.post("/auth/member-login", json={"phone": phone})


async def _needs_member(client: AsyncClient, token: str | None = None):
    """회원 세션이 필요한 요청. 토큰을 주면 이 요청에만 헤더로 붙인다."""
    headers = {HEADER: token} if token else {}
    return await client.post("/book-requests", json={"title": "작별하지 않는다"}, headers=headers)


async def _session_count(session: AsyncSession) -> int:
    return await session.scalar(text("SELECT count(*) FROM member_sessions"))


# --- 휴대폰 번호 로그인 ---


async def test_login(kiosk_client: AsyncClient, member: dict) -> None:
    """[circulation/member-login] 휴대폰 번호 로그인 / 정상 로그인 (응답에 회원 값이 없다)"""
    res = await _login(kiosk_client)
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"member_token", "expires_at"}
    for value in ("M0001", "김비밀", PHONE):
        assert value not in res.text


async def test_login_hyphenated(
    kiosk_client: AsyncClient, session: AsyncSession, member: dict
) -> None:
    """[circulation/member-login] 휴대폰 번호 로그인 / 하이픈을 넣은 번호"""
    res = await _login(kiosk_client, "010-1234-5678")
    assert res.status_code == 200
    stored = await session.scalar(text("SELECT member_id FROM member_sessions"))
    assert stored == member["id"]


async def test_admin_can_login_as_member(admin_client: AsyncClient, member: dict) -> None:
    """[circulation/member-login] 휴대폰 번호 로그인 / 직원 토큰이면 관리자도 쓴다"""
    assert (await _login(admin_client)).status_code == 200


async def test_member_without_phone_cannot_login(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/member-login] 휴대폰 번호 로그인 / 번호가 없는 회원"""
    await add_member(session, library_a.id, "M0002")
    for phone in ("", UNKNOWN):
        assert (await _login(kiosk_client, phone)).status_code == 404
    assert await _session_count(session) == 0


async def test_login_needs_staff_token(client: AsyncClient, member: dict) -> None:
    """[circulation/member-login] 휴대폰 번호 로그인 / 직원 토큰 없이"""
    assert (await _login(client)).status_code == 401


# --- 로그인 실패는 한 가지로 답한다 ---


@pytest.mark.parametrize("phone", [UNKNOWN, "1234", "abcd", "010-1234-56789", "   "])
async def test_login_failure_is_one_answer(
    kiosk_client: AsyncClient, session: AsyncSession, member: dict, phone: str
) -> None:
    """[circulation/member-login] 로그인 실패는 한 가지로 답한다 / 없는 번호, 형식이 틀린 번호"""
    res = await _login(kiosk_client, phone)
    assert res.status_code == 404
    assert res.json()["detail"] == "번호를 확인해 주세요."
    if phone.strip():
        assert phone not in res.text
    assert await _session_count(session) == 0


async def test_phone_not_in_logs(
    kiosk_client: AsyncClient, member: dict, caplog: pytest.LogCaptureFixture
) -> None:
    """[circulation/member-login] 로그인 실패는 한 가지로 답한다 / 번호가 로그에 남지 않음"""
    with caplog.at_level(logging.DEBUG):
        assert (await _login(kiosk_client)).status_code == 200
        assert (await _login(kiosk_client, UNKNOWN)).status_code == 404
    assert PHONE not in caplog.text and UNKNOWN not in caplog.text
    assert "5678" not in caplog.text and "8888" not in caplog.text


# --- 다른 기관의 회원으로 로그인하지 않음 ---


async def test_other_library_phone(
    kiosk_client: AsyncClient, session: AsyncSession, library_b: Tenant
) -> None:
    """[circulation/member-login] 다른 기관의 회원으로 로그인하지 않음 / 다른 기관의 번호"""
    await add_member(session, library_b.id, "B0001", phone=PHONE)
    assert (await _login(kiosk_client)).status_code == 404
    assert await _session_count(session) == 0


async def test_same_phone_two_libraries(
    kiosk_client: AsyncClient,
    kiosk_client_b: AsyncClient,
    session: AsyncSession,
    library_a: Tenant,
    library_b: Tenant,
) -> None:
    """[circulation/member-login] 다른 기관의 회원으로 로그인하지 않음 / 두 기관의 같은 번호"""
    member_a = await add_member(session, library_a.id, "M0001", phone=PHONE)
    member_b = await add_member(session, library_b.id, "B0001", phone=PHONE)
    assert (await _login(kiosk_client)).status_code == 200
    assert (await _login(kiosk_client_b)).status_code == 200
    rows = await session.execute(text("SELECT library_id, member_id FROM member_sessions"))
    assert {tuple(r) for r in rows} == {
        (library_a.id, member_a["id"]),
        (library_b.id, member_b["id"]),
    }


# --- 회원 세션 ---


async def test_session_valid(kiosk_client: AsyncClient, member: dict) -> None:
    """[circulation/member-login] 회원 세션 / 유효한 회원 세션"""
    await login_member(kiosk_client, PHONE)
    assert (await _needs_member(kiosk_client)).status_code == 201


async def test_session_token_missing(kiosk_client: AsyncClient, member: dict) -> None:
    """[circulation/member-login] 회원 세션 / 회원 토큰이 없음"""
    res = await _needs_member(kiosk_client)
    assert res.status_code == 403
    assert res.json()["detail"] == REQUIRED


async def test_session_unknown_token(kiosk_client: AsyncClient, member: dict) -> None:
    """[circulation/member-login] 회원 세션 / 회원 토큰이 없음 (모르는 토큰)"""
    assert (await _needs_member(kiosk_client, "not-a-token")).status_code == 403


async def test_session_expires_after_three_minutes(
    kiosk_client: AsyncClient, member: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[circulation/member-login] 회원 세션 / 3분이 지난 세션"""
    token = (await _login(kiosk_client)).json()["member_token"]
    assert (await _needs_member(kiosk_client, token)).status_code == 201
    later = clock.now() + timedelta(minutes=3, seconds=1)
    monkeypatch.setattr(clock, "now", lambda: later)
    assert (await _needs_member(kiosk_client, token)).status_code == 403


async def test_session_bound_to_kiosk_session(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant, member: dict
) -> None:
    """[circulation/member-login] 회원 세션 / 다른 키오스크 세션의 토큰"""
    token = (await _login(kiosk_client)).json()["member_token"]
    other_staff_token = await add_staff_session(session, library_a.kiosk)
    async with make_client(other_staff_token) as other:
        assert (await _needs_member(other, token)).status_code == 403
    assert (await _needs_member(kiosk_client, token)).status_code == 201


async def test_session_other_library_kiosk(
    kiosk_client: AsyncClient, kiosk_client_b: AsyncClient, member: dict
) -> None:
    """[circulation/member-login] 회원 세션 / 다른 기관의 키오스크"""
    token = (await _login(kiosk_client)).json()["member_token"]
    assert (await _needs_member(kiosk_client_b, token)).status_code == 403


async def test_kiosk_logout_ends_member_session(kiosk_client: AsyncClient, member: dict) -> None:
    """[circulation/member-login] 회원 세션 / 키오스크 로그아웃 (직원 토큰이 먼저 거부된다)"""
    token = (await _login(kiosk_client)).json()["member_token"]
    assert (await kiosk_client.post("/auth/logout")).status_code == 204
    assert (await _needs_member(kiosk_client, token)).status_code == 401


async def test_token_not_stored(
    kiosk_client: AsyncClient, session: AsyncSession, member: dict
) -> None:
    """[circulation/member-login] 회원 세션 / 토큰 원문을 저장하지 않음"""
    token = (await _login(kiosk_client)).json()["member_token"]
    rows = await session.scalars(text("SELECT member_sessions::text FROM member_sessions"))
    assert token not in " ".join(rows)


async def test_second_login_ends_first(kiosk_client: AsyncClient, member: dict) -> None:
    """[circulation/member-login] 회원 세션 / 한 키오스크 세션에는 로그인이 하나(앞 세션을 끊음)"""
    first = (await _login(kiosk_client)).json()["member_token"]
    second = (await _login(kiosk_client)).json()["member_token"]
    assert (await _needs_member(kiosk_client, first)).status_code == 403
    assert (await _needs_member(kiosk_client, second)).status_code == 201


async def test_old_sessions_are_purged(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant, member: dict
) -> None:
    """[circulation/member-login] 회원 세션 / 끝난 지 하루가 지난 행은 다음 로그인에서 정리한다"""
    await _login(kiosk_client)
    await session.execute(
        text("UPDATE member_sessions SET expires_at = :old"),
        {"old": clock.now() - timedelta(days=2)},
    )
    await _login(kiosk_client)
    rows = await session.scalars(text("SELECT expires_at FROM member_sessions"))
    assert all(expires > clock.now() - timedelta(days=1) for expires in rows)


# --- 회원 로그아웃 ---


async def test_logout(kiosk_client: AsyncClient, member: dict) -> None:
    """[circulation/member-login] 회원 로그아웃 / 로그아웃"""
    token = (await _login(kiosk_client)).json()["member_token"]
    res = await kiosk_client.post("/auth/member-logout", headers={HEADER: token})
    assert res.status_code == 204
    assert (await _needs_member(kiosk_client, token)).status_code == 403


async def test_logout_twice(kiosk_client: AsyncClient, member: dict) -> None:
    """[circulation/member-login] 회원 로그아웃 / 두 번 로그아웃 (모르는 토큰, 헤더 없음 포함)"""
    token = (await _login(kiosk_client)).json()["member_token"]
    for headers in ({HEADER: token}, {HEADER: token}, {HEADER: "not-a-token"}, {}):
        assert (await kiosk_client.post("/auth/member-logout", headers=headers)).status_code == 204


async def test_logout_keeps_staff_token(kiosk_client: AsyncClient, member: dict) -> None:
    """[circulation/member-login] 회원 로그아웃 / 직원 로그아웃은 유지"""
    token = (await _login(kiosk_client)).json()["member_token"]
    await kiosk_client.post("/auth/member-logout", headers={HEADER: token})
    assert (await kiosk_client.get("/auth/me")).status_code == 200


async def test_logout_of_other_kiosk_session_token(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant, member: dict
) -> None:
    """[circulation/member-login] 회원 로그아웃 / 다른 키오스크 세션의 토큰으로는 끊을 수 없다"""
    token = (await _login(kiosk_client)).json()["member_token"]
    other_staff_token = await add_staff_session(session, library_a.kiosk)
    async with make_client(other_staff_token) as other:
        res = await other.post("/auth/member-logout", headers={HEADER: token})
        assert res.status_code == 204
    assert (await _needs_member(kiosk_client, token)).status_code == 201


# --- 회원을 지우면 세션도 지운다 ---


async def test_delete_logged_in_member(
    kiosk_client: AsyncClient, admin_client: AsyncClient, session: AsyncSession, member: dict
) -> None:
    """[circulation/member-login] 회원을 지우면 세션도 지운다 / 로그인 중인 회원 삭제"""
    token = (await _login(kiosk_client)).json()["member_token"]
    assert (await admin_client.delete(f"/members/{member['id']}")).status_code == 204
    assert (await _needs_member(kiosk_client, token)).status_code == 403
    assert await _session_count(session) == 0


# --- 역할별 접근 제한 ---


async def test_kiosk_may_login_and_logout(kiosk_client: AsyncClient, member: dict) -> None:
    """[library/staff-auth] 역할별 접근 제한 / 키오스크의 회원 로그인"""
    assert (await _login(kiosk_client)).status_code == 200
    assert (await kiosk_client.post("/auth/member-logout")).status_code == 204


async def test_kiosk_still_cannot_list_members_or_loans(kiosk_client: AsyncClient) -> None:
    """[library/staff-auth] 역할별 접근 제한 / 키오스크의 관리자 전용 API"""
    assert (await kiosk_client.get("/members")).status_code == 403
    assert (await kiosk_client.get("/loans")).status_code == 403
    assert (await kiosk_client.get("/book-requests")).status_code == 403
