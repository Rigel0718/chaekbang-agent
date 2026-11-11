"""시드 실행: DB 연결·마이그레이션·시드 비밀번호를 확인한 뒤 시드를 한 트랜잭션으로 넣는다."""

import sys

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core import clock
from app.core.config import get_settings
from app.core.migrations import head_revision
from app.seed.catalog import seed_catalog
from app.seed.circulation import seed_loans, seed_members
from app.seed.guide import seed_guide
from app.seed.library import seed_libraries

DEFAULT_SEED = 20261102
CONNECT_TIMEOUT_SECONDS = 5

Report = dict[str, tuple[int, int]]


class SeedPreconditionError(Exception):
    pass


async def check_migrations(conn: AsyncConnection) -> None:
    """alembic_version이 head와 같은지 확인한다. 테이블 존재만 보면 뒤처진 리비전을 놓친다."""
    has_version_table = await conn.scalar(text("SELECT to_regclass('alembic_version') IS NOT NULL"))
    current = None
    if has_version_table:
        current = await conn.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
    head = head_revision()
    if current is None:
        raise SeedPreconditionError(
            "마이그레이션이 적용되지 않은 DB입니다. "
            "먼저 `uv run alembic upgrade head`를 실행하세요."
        )
    if current != head:
        raise SeedPreconditionError(
            f"마이그레이션이 최신이 아닙니다 (현재 {current}, 최신 {head}). "
            "`uv run alembic upgrade head`를 실행하세요."
        )


def seed_passwords() -> tuple[str, str]:
    """시드 계정 비밀번호 (.env). 없거나 8자 미만이면 SeedPreconditionError."""
    settings = get_settings()
    admin, kiosk = settings.seed_admin_password, settings.seed_kiosk_password
    if not admin or not kiosk or len(admin) < 8 or len(kiosk) < 8:
        raise SeedPreconditionError(
            "시드 계정 비밀번호가 없습니다. .env에 SEED_ADMIN_PASSWORD와 SEED_KIOSK_PASSWORD를 "
            "8자 이상으로 설정하세요 (.env.example 참고)."
        )
    return admin, kiosk


async def seed_database(conn: AsyncConnection, seed: int = DEFAULT_SEED) -> Report:
    """전제 조건을 확인한 뒤 시드를 넣는다. 커밋은 호출한 쪽이 한다."""
    admin_password, kiosk_password = seed_passwords()
    await check_migrations(conn)
    session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint")
    library_ids, report = await seed_libraries(session, admin_password, kiosk_password)
    report |= await seed_catalog(session, seed, library_ids)
    report |= await seed_members(session, seed, library_ids)
    report |= await seed_loans(session, seed, library_ids, clock.today())
    report |= await seed_guide(session, library_ids, clock.today())
    await session.flush()
    return report


def _describe_target(database_url: str) -> str:
    url = make_url(database_url)
    return f"{url.host}:{url.port or 5432}/{url.database}"


async def run(database_url: str, seed: int = DEFAULT_SEED) -> int:
    """종료 코드를 돌려준다. 실패하면 데이터를 쓰지 않고 stderr에 한 줄 안내를 출력한다."""
    engine = create_async_engine(
        database_url, poolclass=NullPool, connect_args={"timeout": CONNECT_TIMEOUT_SECONDS}
    )
    try:
        try:
            conn = await engine.connect()
        except (OSError, TimeoutError, DBAPIError) as exc:
            print(
                f"DB에 연결할 수 없습니다 ({_describe_target(database_url)}, "
                f"{type(exc).__name__}). `docker compose up -d db`로 DB를 실행했는지, "
                "DATABASE_URL이 맞는지 확인하세요.",
                file=sys.stderr,
            )
            return 1
        try:
            async with conn.begin():
                report = await seed_database(conn, seed)
        except SeedPreconditionError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        finally:
            await conn.close()
    finally:
        await engine.dispose()

    for table, (created, skipped) in report.items():
        print(f"{table}: 생성 {created}건, 건너뜀 {skipped}건")
    return 0
