"""platform/database-schema 스펙 테스트."""

import asyncio
from datetime import date

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core.migrations import alembic_config
from app.models import SHARED_TABLES, TENANT_TABLES, Base
from tests.conftest import Tenant
from tests.helpers import add_book, add_holding, add_member, assert_rejected

ALL_TABLES = {
    "libraries",
    "staff_users",
    "staff_sessions",
    "books",
    "holdings",
    "members",
    "loans",
}


async def _table_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        names = await conn.run_sync(lambda c: inspect(c).get_table_names())
    return set(names) - {"alembic_version"}


async def test_upgrade_creates_all_tables(engine: AsyncEngine) -> None:
    """[platform/database-schema] 마이그레이션으로 스키마 생성 / 빈 DB에 upgrade

    conftest의 migrated_db가 base로 내린 뒤 head까지 올린 DB다.
    """
    assert await _table_names(engine) == ALL_TABLES
    assert len(ALL_TABLES) == 7


async def test_downgrade_then_upgrade_again(engine: AsyncEngine, migrated_db: str) -> None:
    """[platform/database-schema] 마이그레이션으로 스키마 생성 / downgrade 후 재적용"""
    config = alembic_config(migrated_db)
    await asyncio.to_thread(command.downgrade, config, "base")
    assert await _table_names(engine) == set()
    await asyncio.to_thread(command.upgrade, config, "head")
    assert await _table_names(engine) == ALL_TABLES


async def test_models_match_migrations(engine: AsyncEngine) -> None:
    """[platform/database-schema] 마이그레이션으로 스키마 생성 / 모델과 마이그레이션 일치"""

    def diff(sync_conn):
        return compare_metadata(MigrationContext.configure(sync_conn), Base.metadata)

    async with engine.connect() as conn:
        assert await conn.run_sync(diff) == []


async def test_every_table_is_shared_or_tenant(engine: AsyncEngine) -> None:
    """[platform/database-schema] 기관 데이터 테이블 구분 / 구분되지 않은 테이블"""
    assert not SHARED_TABLES & TENANT_TABLES, "둘 다에 속한 테이블이 있다"
    assert await _table_names(engine) == SHARED_TABLES | TENANT_TABLES


async def test_tenant_tables_have_library_id(engine: AsyncEngine) -> None:
    """[platform/database-schema] 기관 데이터 테이블 구분 / library_id 누락"""

    def collect(sync_conn):
        insp = inspect(sync_conn)
        return {
            table: (
                {c["name"]: c for c in insp.get_columns(table)},
                insp.get_foreign_keys(table),
            )
            for table in TENANT_TABLES
        }

    async with engine.connect() as conn:
        tables = await conn.run_sync(collect)
    for table, (columns, fks) in tables.items():
        assert "library_id" in columns, table
        assert columns["library_id"]["nullable"] is False, table
        assert any(
            fk["constrained_columns"] == ["library_id"]
            and fk["referred_table"] == "libraries"
            and fk["referred_columns"] == ["id"]
            for fk in fks
        ), f"{table}에 libraries 외래 키가 없다"


async def test_loan_rejects_holding_of_other_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[platform/database-schema] 기관 간 참조 금지 / 다른 기관 사본으로 대출 직접 저장"""
    book = await add_book(session)
    holding_b = await add_holding(session, library_b.id, book["id"], "EM0001")
    member_a = await add_member(session, library_a.id, "M0001")
    await assert_rejected(
        session,
        "loans",
        library_id=library_a.id,
        holding_id=holding_b["id"],
        member_id=member_a["id"],
        loaned_on=date(2026, 11, 1),
        due_on=date(2026, 11, 15),
        match="fk_loans_library_id_holding_id_holdings",
    )


async def test_loan_rejects_member_of_other_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[platform/database-schema] 기관 간 참조 금지 / 다른 기관 회원으로 대출 직접 저장"""
    book = await add_book(session)
    holding_a = await add_holding(session, library_a.id, book["id"], "EM0001")
    member_b = await add_member(session, library_b.id, "M0001")
    await assert_rejected(
        session,
        "loans",
        library_id=library_a.id,
        holding_id=holding_a["id"],
        member_id=member_b["id"],
        loaned_on=date(2026, 11, 1),
        due_on=date(2026, 11, 15),
        match="fk_loans_library_id_member_id_members",
    )
