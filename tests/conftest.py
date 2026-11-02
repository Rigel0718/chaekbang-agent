"""테스트 공통 fixture.

테스트 DB(TEST_DATABASE_URL)에 세션 시작 시 마이그레이션을 새로 적용하고,
각 테스트는 연결 단위 트랜잭션 안에서 돌린 뒤 롤백한다.
"""

import asyncio
from collections.abc import AsyncIterator

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
async def client(session: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override_get_session() -> AsyncIterator[AsyncSession]:
        yield session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
