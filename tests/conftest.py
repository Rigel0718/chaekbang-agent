"""테스트 공통 fixture.

테스트 DB(TEST_DATABASE_URL)에 세션 시작 시 마이그레이션을 새로 적용하고,
각 테스트는 연결 단위 트랜잭션 안에서 돌린 뒤 롤백한다.
"""

import asyncio
import os
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

# 비밀번호 해시 비용을 낮춰 계정을 많이 만드는 테스트를 빠르게 한다 (설정을 읽기 전에 정한다).
os.environ["PASSWORD_SCRYPT_N"] = "1024"
# 시드 테스트용 계정 비밀번호 (.env에 없어도 테스트가 돌게 한다)
os.environ.setdefault("SEED_ADMIN_PASSWORD", "seed-admin-pass")
os.environ.setdefault("SEED_KIOSK_PASSWORD", "seed-kiosk-pass")

import pytest
from alembic import command
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.core.db import get_session
from app.core.migrations import alembic_config
from app.main import app
from tests.helpers import add_library, add_staff, add_staff_session


def _test_database_url() -> str:
    url = get_settings().test_database_url
    if not url:
        pytest.exit("TEST_DATABASE_URL이 설정되지 않았습니다. .env.example을 참고하세요.", 1)
    return url


@pytest.fixture(scope="session")
def test_database_url() -> str:
    return _test_database_url()


async def _ping(url: str) -> None:
    engine = create_async_engine(url, poolclass=NullPool, connect_args={"timeout": 5})
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def migrated_db(test_database_url: str) -> str:
    try:
        asyncio.run(_ping(test_database_url))
    except Exception as exc:  # noqa: BLE001 - 원인과 상관없이 안내 후 종료
        pytest.exit(
            f"테스트 DB에 연결할 수 없습니다 ({type(exc).__name__}). "
            "`docker compose up -d db`로 DB를 먼저 실행하세요.",
            1,
        )
    config = alembic_config(test_database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    return test_database_url


@pytest.fixture(scope="session")
async def engine(migrated_db: str) -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(migrated_db, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """테스트가 끝나면 모든 변경을 롤백하는 세션. service의 commit은 savepoint로 처리된다."""
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


@pytest.fixture
async def _app(session: AsyncSession) -> AsyncIterator[None]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override_get_session
    yield
    app.dependency_overrides.clear()


def make_client(token: str | None = None) -> AsyncClient:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=headers)


@pytest.fixture
async def client(_app: None) -> AsyncIterator[AsyncClient]:
    """토큰 없는 클라이언트."""
    async with make_client() as client:
        yield client


@dataclass
class Tenant:
    """테스트용 기관 하나와 그 기관의 관리자·키오스크 계정, 발급된 토큰."""

    library: Any
    admin: Any
    kiosk: Any
    admin_token: str
    kiosk_token: str

    @property
    def id(self) -> int:
        return self.library["id"]


async def _tenant(session: AsyncSession, name: str, loan_mode: str, prefix: str) -> Tenant:
    library = await add_library(session, name=name, loan_mode=loan_mode)
    admin = await add_staff(session, library["id"], f"{prefix}-admin", role="admin")
    kiosk = await add_staff(session, library["id"], f"{prefix}-kiosk", role="kiosk")
    return Tenant(
        library=library,
        admin=admin,
        kiosk=kiosk,
        admin_token=await add_staff_session(session, admin),
        kiosk_token=await add_staff_session(session, kiosk),
    )


@pytest.fixture
async def library_a(session: AsyncSession) -> Tenant:
    """자체 대출 기관 (loan_mode=internal, 기본 대출 기간 14일)."""
    return await _tenant(session, "A 작은도서관", "internal", "a")


@pytest.fixture
async def library_b(session: AsyncSession) -> Tenant:
    """가져오기 기관 (loan_mode=imported)."""
    return await _tenant(session, "B 작은도서관", "imported", "b")


@pytest.fixture
async def admin_client(_app: None, library_a: Tenant) -> AsyncIterator[AsyncClient]:
    async with make_client(library_a.admin_token) as client:
        yield client


@pytest.fixture
async def kiosk_client(_app: None, library_a: Tenant) -> AsyncIterator[AsyncClient]:
    async with make_client(library_a.kiosk_token) as client:
        yield client


@pytest.fixture
async def admin_client_b(_app: None, library_b: Tenant) -> AsyncIterator[AsyncClient]:
    async with make_client(library_b.admin_token) as client:
        yield client


@pytest.fixture
async def kiosk_client_b(_app: None, library_b: Tenant) -> AsyncIterator[AsyncClient]:
    async with make_client(library_b.kiosk_token) as client:
        yield client
