"""platform/dev-seed-data 스펙 테스트.

생성 규칙은 테스트 트랜잭션 안에서 seed_database()를 직접 불러 확인하고,
실행 전제 조건과 종료 코드는 별도 임시 DB를 만들어 scripts/seed.py를 subprocess로 실행해 확인한다.
"""

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator

import pytest
from alembic import command
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.migrations import PROJECT_ROOT, alembic_config
from app.matching.isbn import normalize_isbn
from app.seed.runner import SeedPreconditionError, seed_database

SEED_DB = "chaekbang_seed_test"


async def _count(session: AsyncSession, table: str) -> int:
    return await session.scalar(text(f"SELECT count(*) FROM {table}"))


async def _seed(session: AsyncSession) -> dict:
    return await seed_database(await session.connection())


# --- 생성 규칙 (테스트 트랜잭션 안에서 실행, 끝나면 롤백) ---


async def test_seed_creates_expected_rows(session: AsyncSession) -> None:
    """[platform/dev-seed-data] 시드 데이터 생성 / 빈 DB에 시드 실행"""
    report = await _seed(session)
    assert report["books"] == (50, 0)
    assert await _count(session, "books") == 50
    inventory = await _count(session, "store_inventory")
    assert 1 <= inventory < 50
    assert await _count(session, "institutions") == 3
    types = set(await session.scalars(text("SELECT DISTINCT type FROM institutions")))
    assert types == {"school", "daycare", "community_center"}
    # 재고가 없는 책과 품절(수량 0) 책이 둘 다 있다
    assert await session.scalar(text("SELECT count(*) FROM store_inventory WHERE quantity = 0"))


async def test_seed_respects_domain_rules(session: AsyncSession) -> None:
    """[platform/dev-seed-data] 시드 데이터 생성 / 시드 데이터가 도메인 규칙을 지킴"""
    await _seed(session)
    rows = (await session.execute(text("SELECT isbn, list_price FROM books"))).all()
    for isbn, price in rows:
        assert normalize_isbn(isbn) == isbn
        assert isinstance(price, int) and price >= 0


async def test_seed_twice_does_not_duplicate(session: AsyncSession) -> None:
    """[platform/dev-seed-data] 반복 실행 안전성 / 두 번 실행"""
    await _seed(session)
    first = {t: await _count(session, t) for t in ("books", "store_inventory", "institutions")}
    report = await _seed(session)
    second = {t: await _count(session, t) for t in ("books", "store_inventory", "institutions")}
    assert (
        first
        == second
        == {"books": 50, "store_inventory": first["store_inventory"], "institutions": 3}
    )
    assert report["books"] == (0, 50)
    assert report["institutions"] == (0, 3)


async def test_seed_is_deterministic(session: AsyncSession) -> None:
    """[platform/dev-seed-data] 반복 실행 안전성 (같은 시드 값이면 같은 데이터)"""
    from app.seed.catalog import generate_books

    assert generate_books(1) == generate_books(1)
    assert generate_books(1) != generate_books(2)


async def test_seed_refuses_when_migration_is_behind(session: AsyncSession) -> None:
    """[platform/dev-seed-data] 실행 전제 조건 확인 / 마이그레이션이 최신이 아님"""
    await session.execute(text("UPDATE alembic_version SET version_num = '000000000000'"))
    with pytest.raises(SeedPreconditionError, match="alembic upgrade head"):
        await _seed(session)
    assert await _count(session, "books") == 0


async def test_seed_refuses_without_version_table(session: AsyncSession) -> None:
    """[platform/dev-seed-data] 실행 전제 조건 확인 / 마이그레이션 전 실행 (버전 기록 없음)"""
    await session.execute(text("DROP TABLE alembic_version"))
    with pytest.raises(SeedPreconditionError, match="alembic upgrade head"):
        await _seed(session)
    assert await _count(session, "books") == 0


# --- 실제 스크립트 실행 (임시 DB, subprocess) ---


def _run_script(database_url: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "DATABASE_URL": database_url}
    return subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "seed.py")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


@pytest.fixture
async def empty_db_url(migrated_db: str) -> AsyncIterator[str]:
    """테이블이 하나도 없는 임시 DB. 테스트가 끝나면 지운다."""
    admin = create_async_engine(migrated_db, poolclass=NullPool, isolation_level="AUTOCOMMIT")
    async with admin.connect() as conn:
        await conn.execute(text(f"DROP DATABASE IF EXISTS {SEED_DB} WITH (FORCE)"))
        await conn.execute(text(f"CREATE DATABASE {SEED_DB}"))
    url = make_url(migrated_db).set(database=SEED_DB).render_as_string(hide_password=False)
    try:
        yield url
    finally:
        async with admin.connect() as conn:
            await conn.execute(text(f"DROP DATABASE IF EXISTS {SEED_DB} WITH (FORCE)"))
        await admin.dispose()


async def _table_count(url: str) -> int:
    engine = create_async_engine(url, poolclass=NullPool)
    async with engine.connect() as conn:
        count = await conn.scalar(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
        )
    await engine.dispose()
    return count


async def test_script_before_migration(empty_db_url: str) -> None:
    """[platform/dev-seed-data] 실행 전제 조건 확인 / 마이그레이션 전 실행"""
    result = await asyncio.to_thread(_run_script, empty_db_url)
    assert result.returncode != 0
    assert "alembic upgrade head" in result.stderr
    assert "Traceback" not in result.stderr
    assert len(result.stderr.strip().splitlines()) == 1
    assert await _table_count(empty_db_url) == 0


async def test_script_cannot_connect() -> None:
    """[platform/dev-seed-data] 실행 전제 조건 확인 / DB에 연결할 수 없음"""
    url = "postgresql+asyncpg://chaekbang:s3cret-pw@127.0.0.1:1/nowhere"
    result = await asyncio.to_thread(_run_script, url)
    assert result.returncode != 0
    assert "127.0.0.1:1/nowhere" in result.stderr
    assert "docker compose up -d db" in result.stderr
    assert "s3cret-pw" not in result.stderr
    assert "Traceback" not in result.stderr


async def test_script_success_and_rerun(empty_db_url: str) -> None:
    """[platform/dev-seed-data] 실행 전제 조건 확인 / 정상 실행 (+ 반복 실행 안전성)"""
    await asyncio.to_thread(command.upgrade, alembic_config(empty_db_url), "head")

    first = await asyncio.to_thread(_run_script, empty_db_url)
    assert first.returncode == 0, first.stderr
    assert "books: 생성 50건, 건너뜀 0건" in first.stdout
    assert "institutions: 생성 3건, 건너뜀 0건" in first.stdout

    second = await asyncio.to_thread(_run_script, empty_db_url)
    assert second.returncode == 0, second.stderr
    assert "books: 생성 0건, 건너뜀 50건" in second.stdout
