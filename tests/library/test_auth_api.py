"""[library/staff-auth] 로그인과 토큰, 토큰 검증과 로그아웃."""

from datetime import datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from tests.conftest import Tenant, make_client
from tests.helpers import TEST_PASSWORD, add_staff_session

DEACTIVATE_KIOSK = text("UPDATE staff_users SET is_active = false WHERE login_id = 'a-kiosk'")


async def _login(client: AsyncClient, login_id: str, password: str = TEST_PASSWORD):
    return await client.post("/auth/login", json={"login_id": login_id, "password": password})


async def test_login(client: AsyncClient, library_a: Tenant) -> None:
    """[library/staff-auth] 로그인과 토큰 / 정상 로그인"""
    before = clock.now()
    res = await _login(client, "a-admin")
    assert res.status_code == 200
    body = res.json()
    assert body["token"]
    assert body["role"] == "admin"
    # 관리자 토큰은 설정의 12시간 뒤 만료
    expires = datetime.fromisoformat(body["expires_at"])
    assert before + timedelta(hours=11) < expires < before + timedelta(hours=13)

    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200


async def test_kiosk_token_lasts_longer(client: AsyncClient, library_a: Tenant) -> None:
    """[library/staff-auth] 로그인과 토큰 (토큰 만료 시간은 역할마다 다름)"""
    before = clock.now()
    body = (await _login(client, "a-kiosk")).json()
    assert body["role"] == "kiosk"
    assert datetime.fromisoformat(body["expires_at"]) > before + timedelta(days=29)


async def test_wrong_password_and_unknown_id(client: AsyncClient, library_a: Tenant) -> None:
    """[library/staff-auth] 로그인과 토큰 / 틀린 비밀번호와 없는 아이디"""
    wrong = await _login(client, "a-admin", "wrong-password")
    unknown = await _login(client, "nobody")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


async def test_inactive_account_login(
    client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/staff-auth] 로그인과 토큰 / 사용 중지된 계정"""
    await session.execute(DEACTIVATE_KIOSK)
    res = await _login(client, "a-kiosk")
    assert res.status_code == 401
    assert res.json() == (await _login(client, "nobody")).json()


async def test_me(admin_client: AsyncClient) -> None:
    """[library/staff-auth] 로그인과 토큰 / 내 정보 조회"""
    res = await admin_client.get("/auth/me")
    assert res.status_code == 200
    body = res.json()
    assert (body["login_id"], body["role"], body["library_name"]) == (
        "a-admin",
        "admin",
        "A 작은도서관",
    )


async def test_no_token(client: AsyncClient) -> None:
    """[library/staff-auth] 토큰 검증과 로그아웃 / 토큰 없이 호출 (모르는 토큰 포함)"""
    assert (await client.get("/auth/me")).status_code == 401
    res = await client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert res.status_code == 401


async def test_expired_token(_app, session: AsyncSession, library_a: Tenant) -> None:
    """[library/staff-auth] 토큰 검증과 로그아웃 / 만료된 토큰"""
    token = await add_staff_session(session, library_a.admin, expires_in=timedelta(seconds=-1))
    async with make_client(token) as c:
        assert (await c.get("/auth/me")).status_code == 401


async def test_logout(admin_client: AsyncClient) -> None:
    """[library/staff-auth] 토큰 검증과 로그아웃 / 로그아웃한 토큰"""
    assert (await admin_client.post("/auth/logout")).status_code == 204
    assert (await admin_client.get("/auth/me")).status_code == 401


async def test_logout_only_ends_that_token(
    _app, admin_client: AsyncClient, library_a: Tenant, session: AsyncSession
) -> None:
    """[library/staff-auth] 토큰 검증과 로그아웃 (다른 세션은 유지)"""
    other = await add_staff_session(session, library_a.admin)
    await admin_client.post("/auth/logout")
    async with make_client(other) as c:
        assert (await c.get("/auth/me")).status_code == 200


async def test_token_after_deactivation(kiosk_client: AsyncClient, session: AsyncSession) -> None:
    """[library/staff-auth] 토큰 검증과 로그아웃 / 사용 중지 후 기존 토큰 (DB에서 사용 중지)"""
    assert (await kiosk_client.get("/auth/me")).status_code == 200
    await session.execute(DEACTIVATE_KIOSK)
    assert (await kiosk_client.get("/auth/me")).status_code == 401
