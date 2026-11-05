"""[library/staff-auth] 직원 계정과 역할, 직원 계정 관리."""

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Tenant, make_client
from tests.helpers import assert_rejected


async def _login(client: AsyncClient, login_id: str, password: str):
    return await client.post("/auth/login", json={"login_id": login_id, "password": password})


async def test_create_kiosk_account(
    admin_client: AsyncClient, client: AsyncClient, library_a: Tenant
) -> None:
    """[library/staff-auth] 직원 계정 관리 / 키오스크 계정 만들기"""
    res = await admin_client.post(
        "/staff", json={"login_id": "a-kiosk-2", "password": "kiosk-pass-1", "role": "kiosk"}
    )
    assert res.status_code == 201
    body = res.json()
    assert body["role"] == "kiosk"
    assert "password_hash" not in body and "password" not in body
    assert (await _login(client, "a-kiosk-2", "kiosk-pass-1")).status_code == 200

    listed = (await admin_client.get("/staff")).json()
    assert {s["login_id"] for s in listed["items"]} == {"a-admin", "a-kiosk", "a-kiosk-2"}


async def test_password_not_stored(admin_client: AsyncClient, session: AsyncSession) -> None:
    """[library/staff-auth] 직원 계정과 역할 / 비밀번호 원문 미저장"""
    await admin_client.post(
        "/staff", json={"login_id": "a-new", "password": "library-pass-1", "role": "admin"}
    )
    row = (
        (await session.execute(text("SELECT * FROM staff_users WHERE login_id = 'a-new'")))
        .mappings()
        .one()
    )
    assert all("library-pass-1" not in str(v) for v in row.values())


async def test_invalid_role_rejected_by_db(session: AsyncSession, library_a: Tenant) -> None:
    """[library/staff-auth] 직원 계정과 역할 / 허용되지 않은 역할"""
    await assert_rejected(
        session,
        "staff_users",
        library_id=library_a.id,
        login_id="owner-1",
        password_hash="x",
        role="owner",
    )


async def test_duplicate_login_id(admin_client: AsyncClient, library_b: Tenant) -> None:
    """[library/staff-auth] 직원 계정 관리 / 중복 아이디 (다른 기관 아이디와도 겹칠 수 없음)"""
    res = await admin_client.post(
        "/staff", json={"login_id": "b-admin", "password": "long-enough", "role": "admin"}
    )
    assert res.status_code == 409


async def test_short_password(admin_client: AsyncClient) -> None:
    """[library/staff-auth] 직원 계정 관리 / 짧은 비밀번호"""
    res = await admin_client.post(
        "/staff", json={"login_id": "a-short", "password": "7-chars", "role": "kiosk"}
    )
    assert res.status_code == 422


async def test_cannot_deactivate_self(admin_client: AsyncClient, library_a: Tenant) -> None:
    """[library/staff-auth] 직원 계정 관리 / 자기 계정 사용 중지 (역할을 키오스크로 바꾸기 포함)"""
    me = library_a.admin["id"]
    assert (await admin_client.patch(f"/staff/{me}", json={"is_active": False})).status_code == 409
    assert (await admin_client.patch(f"/staff/{me}", json={"role": "kiosk"})).status_code == 409
    assert (await admin_client.get("/auth/me")).json()["role"] == "admin"


async def test_deactivate_kiosk_ends_token(
    admin_client: AsyncClient, kiosk_client: AsyncClient, library_a: Tenant
) -> None:
    """[library/staff-auth] 토큰 검증과 로그아웃 / 사용 중지 후 기존 토큰"""
    res = await admin_client.patch(f"/staff/{library_a.kiosk['id']}", json={"is_active": False})
    assert res.status_code == 200
    assert (await kiosk_client.get("/library")).status_code == 401


async def test_password_change_revokes_tokens(
    admin_client: AsyncClient, kiosk_client: AsyncClient, client: AsyncClient, library_a: Tenant
) -> None:
    """[library/staff-auth] 토큰 검증과 로그아웃 / 비밀번호 변경 후 기존 토큰"""
    res = await admin_client.patch(
        f"/staff/{library_a.kiosk['id']}", json={"password": "new-kiosk-pass"}
    )
    assert res.status_code == 200
    assert (await kiosk_client.get("/library")).status_code == 401
    assert (await _login(client, "a-kiosk", "new-kiosk-pass")).status_code == 200
    # 관리자 자신의 토큰은 그대로
    assert (await admin_client.get("/library")).status_code == 200


async def test_role_change_applies_to_existing_token(
    admin_client: AsyncClient, kiosk_client: AsyncClient, library_a: Tenant
) -> None:
    """[library/staff-auth] 토큰 검증과 로그아웃 (역할은 요청마다 계정에서 읽는다)"""
    assert (await kiosk_client.get("/staff")).status_code == 403
    await admin_client.patch(f"/staff/{library_a.kiosk['id']}", json={"role": "admin"})
    assert (await kiosk_client.get("/staff")).status_code == 200


async def test_other_library_staff_is_404(
    admin_client: AsyncClient, library_b: Tenant, session: AsyncSession
) -> None:
    """[library/libraries] 기관 데이터 분리 (다른 기관 직원 수정은 404)"""
    res = await admin_client.patch(f"/staff/{library_b.kiosk['id']}", json={"is_active": False})
    assert res.status_code == 404
    active = await session.scalar(
        text("SELECT is_active FROM staff_users WHERE id = :id"), {"id": library_b.kiosk["id"]}
    )
    assert active is True
    listed = (await admin_client.get("/staff")).json()
    assert all(not s["login_id"].startswith("b-") for s in listed["items"])


async def test_kiosk_cannot_manage_staff(_app, library_a: Tenant) -> None:
    """[library/staff-auth] 역할별 접근 제한 (직원 관리는 관리자만)"""
    async with make_client(library_a.kiosk_token) as c:
        assert (await c.get("/staff")).status_code == 403
        payload = {"login_id": "x", "password": "12345678", "role": "admin"}
        res = await c.post("/staff", json=payload)
        assert res.status_code == 403
