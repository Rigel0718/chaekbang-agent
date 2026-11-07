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

from app.core import clock
from app.core.config import get_settings
from app.core.isbn import normalize_isbn
from app.core.migrations import PROJECT_ROOT, alembic_config
from app.core.security import verify_password
from app.seed.runner import SeedPreconditionError, seed_database

SEED_DB = "chaekbang_seed_test"


async def _count(session: AsyncSession, table: str) -> int:
    return await session.scalar(text(f"SELECT count(*) FROM {table}"))


async def _seed(session: AsyncSession) -> dict:
    return await seed_database(await session.connection())


# --- 생성 규칙 (테스트 트랜잭션 안에서 실행, 끝나면 롤백) ---

TABLES = (
    "libraries",
    "staff_users",
    "books",
    "library_books",
    "library_book_audiences",
    "holdings",
    "members",
    "loans",
)


async def test_seed_creates_expected_rows(session: AsyncSession) -> None:
    """[platform/dev-seed-data] 시드 데이터 생성 / 빈 DB에 시드 실행"""
    report = await _seed(session)
    assert report["books"] == (45, 0)
    assert await _count(session, "libraries") == 2
    modes = set(await session.scalars(text("SELECT loan_mode FROM libraries")))
    assert modes == {"internal", "imported"}

    staff = (
        await session.execute(
            text(
                "SELECT l.loan_mode, s.role FROM staff_users s"
                " JOIN libraries l ON l.id = s.library_id"
            )
        )
    ).all()
    assert sorted(staff) == sorted(
        [("internal", "admin"), ("internal", "kiosk"), ("imported", "admin"), ("imported", "kiosk")]
    )

    assert await _count(session, "books") == 45
    assert not await session.scalar(text("SELECT count(*) FROM books WHERE isbn IS NULL"))
    per_library_books = (
        await session.execute(
            text(
                "SELECT library_id,"
                " count(*) FILTER (WHERE isbn IS NULL),"
                " count(*) FILTER (WHERE book_id IS NOT NULL)"
                " FROM library_books GROUP BY library_id"
            )
        )
    ).all()
    assert len(per_library_books) == 2
    for _library, no_isbn, linked in per_library_books:
        assert no_isbn >= 1 and linked >= 1
    children = await session.execute(
        text(
            "SELECT count(DISTINCT library_id) FROM library_book_audiences"
            " WHERE audience = 'children'"
        )
    )
    assert children.scalar() == 2
    # 같은 ISBN을 두 기관이 함께 가진 경우
    assert await session.scalar(
        text(
            "SELECT count(*) FROM (SELECT isbn FROM library_books WHERE isbn IS NOT NULL"
            " GROUP BY isbn HAVING count(*) > 1) t"
        )
    )

    per_library = (
        await session.execute(
            text(
                "SELECT l.loan_mode,"
                " count(*) FILTER (WHERE h.acquisition_type = 'purchased'),"
                " count(*) FILTER (WHERE h.acquisition_type = 'donated'),"
                " count(DISTINCT h.library_book_id)"
                " FROM holdings h JOIN libraries l ON l.id = h.library_id GROUP BY l.loan_mode"
            )
        )
    ).all()
    assert len(per_library) == 2
    for _mode, purchased, donated, books in per_library:
        assert purchased >= 1 and donated >= 1
        assert books < 50  # 소장하지 않은 책이 있다
    # 같은 책 여러 권, 분실·훼손 사본
    assert await session.scalar(
        text(
            "SELECT count(*) FROM (SELECT 1 FROM holdings GROUP BY library_id, library_book_id"
            " HAVING count(*) > 1) t"
        )
    )
    statuses = set(await session.scalars(text("SELECT DISTINCT status FROM holdings")))
    assert {"lost", "damaged"} <= statuses

    assert await _count(session, "members") == 20
    loans = (
        (
            await session.execute(
                text(
                    "SELECT DISTINCT l.loan_mode FROM loans"
                    " JOIN libraries l ON l.id = loans.library_id"
                )
            )
        )
        .scalars()
        .all()
    )
    assert loans == ["internal"]
    today = clock.today()
    overdue = await session.scalar(
        text("SELECT count(*) FROM loans WHERE returned_on IS NULL AND due_on < :t"), {"t": today}
    )
    active = await session.scalar(
        text("SELECT count(*) FROM loans WHERE returned_on IS NULL AND due_on >= :t"), {"t": today}
    )
    returned = await session.scalar(
        text("SELECT count(*) FROM loans WHERE returned_on IS NOT NULL")
    )
    assert (returned, active, overdue) == (5, 5, 3)


async def test_seed_respects_domain_rules(session: AsyncSession) -> None:
    """[platform/dev-seed-data] 시드 데이터 생성 / 시드 데이터가 도메인 규칙을 지킴"""
    await _seed(session)
    for table in ("books", "library_books"):
        rows = (await session.execute(text(f"SELECT isbn, list_price FROM {table}"))).all()
        for isbn, price in rows:
            if isbn is not None:
                assert normalize_isbn(isbn) == isbn
            assert price is None or (isinstance(price, int) and price >= 0)

    holdings = (
        await session.execute(
            text(
                "SELECT h.acquisition_type, h.purchase_price, b.isbn FROM holdings h"
                " JOIN library_books b ON b.id = h.library_book_id"
            )
        )
    ).all()
    for acquisition, purchase_price, isbn in holdings:
        assert purchase_price is None or purchase_price >= 0
        if acquisition == "purchased":
            assert purchase_price is not None and isbn is not None

    on_loan_mismatch = await session.scalar(
        text(
            "SELECT count(*) FROM holdings h WHERE (h.status = 'on_loan') <>"
            " EXISTS (SELECT 1 FROM loans l WHERE l.holding_id = h.id AND l.returned_on IS NULL)"
        )
    )
    assert on_loan_mismatch == 0

    # 시드 계정으로 로그인할 수 있다: 로그인 service와 같은 조건(비밀번호 검증, 사용 중)을 본다.
    # (로그인 service는 커밋하므로 시드를 넣은 같은 트랜잭션 안에서는 부르지 않는다)
    settings = get_settings()
    accounts = dict(
        (
            await session.execute(
                text("SELECT login_id, password_hash FROM staff_users WHERE is_active")
            )
        ).all()
    )
    for login_id, password in (
        ("sunny-admin", settings.seed_admin_password),
        ("sunny-kiosk", settings.seed_kiosk_password),
        ("forest-admin", settings.seed_admin_password),
        ("forest-kiosk", settings.seed_kiosk_password),
    ):
        assert verify_password(password, accounts[login_id]), login_id


async def test_seed_twice_does_not_duplicate(session: AsyncSession) -> None:
    """[platform/dev-seed-data] 반복 실행 안전성 / 두 번 실행"""
    await _seed(session)
    first = {t: await _count(session, t) for t in TABLES}
    report = await _seed(session)
    second = {t: await _count(session, t) for t in TABLES}
    assert first == second
    assert all(created == 0 for created, _ in report.values()), report


async def test_seed_is_deterministic(session: AsyncSession) -> None:
    """[platform/dev-seed-data] 반복 실행 안전성 (같은 시드 값이면 같은 데이터)"""
    from app.seed.catalog import generate_books, generate_holdings

    assert generate_books(1) == generate_books(1)
    assert generate_books(1) != generate_books(2)
    books = generate_books(1)
    assert generate_holdings(1, books, "sunny", 1) == generate_holdings(1, books, "sunny", 1)


async def test_seed_requires_passwords(
    session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[platform/dev-seed-data] 시드 데이터 생성 (시드 비밀번호가 없으면 아무것도 쓰지 않음)"""
    monkeypatch.setattr(get_settings(), "seed_admin_password", None)
    with pytest.raises(SeedPreconditionError, match="SEED_ADMIN_PASSWORD"):
        await _seed(session)
    assert await _count(session, "libraries") == 0


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
    assert "books: 생성 45건, 건너뜀 0건" in first.stdout
    assert "libraries: 생성 2건, 건너뜀 0건" in first.stdout
    assert "loans: 생성 13건, 건너뜀 0건" in first.stdout

    second = await asyncio.to_thread(_run_script, empty_db_url)
    assert second.returncode == 0, second.stderr
    assert "books: 생성 0건, 건너뜀 45건" in second.stdout
    assert "생성 0건" in second.stdout
    assert all("생성 0건" in line for line in second.stdout.strip().splitlines())
