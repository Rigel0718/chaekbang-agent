"""platform/database-schema 스펙 테스트."""

import asyncio

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.migrations import alembic_config
from app.models import CONTEXT_TABLES, Base

ALL_TABLES = set().union(*CONTEXT_TABLES.values())


def _context_of(table: str) -> str:
    return next(ctx for ctx, tables in CONTEXT_TABLES.items() if table in tables)


async def _table_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as conn:
        names = await conn.run_sync(lambda c: inspect(c).get_table_names())
    return set(names) - {"alembic_version"}


async def _foreign_keys(engine: AsyncEngine) -> list[tuple[str, str]]:
    def collect(sync_conn) -> list[tuple[str, str]]:
        insp = inspect(sync_conn)
        return [
            (table, fk["referred_table"])
            for table in insp.get_table_names()
            for fk in insp.get_foreign_keys(table)
        ]

    async with engine.connect() as conn:
        return await conn.run_sync(collect)


async def test_every_table_belongs_to_exactly_one_context(engine: AsyncEngine) -> None:
    """[platform/database-schema] 컨텍스트별 테이블 소유 / 소유 컨텍스트가 없는 테이블"""
    owned = [t for tables in CONTEXT_TABLES.values() for t in tables]
    assert len(owned) == len(set(owned)), "둘 이상의 컨텍스트에 속한 테이블이 있다"
    assert await _table_names(engine) == set(owned)


async def test_cross_context_foreign_keys_only_point_to_catalog(engine: AsyncEngine) -> None:
    """[platform/database-schema] 컨텍스트 간 참조 방향 / 외래 키 방향 점검"""
    fks = await _foreign_keys(engine)
    assert fks, "외래 키를 하나도 찾지 못했다"
    for table, referred in fks:
        src, dst = _context_of(table), _context_of(referred)
        if src != dst:
            assert dst == "catalog", f"{table}({src}) → {referred}({dst})"
        if src == "catalog":
            assert dst == "catalog", f"catalog 테이블 {table}이 {referred}를 참조한다"


async def test_upgrade_creates_all_tables(engine: AsyncEngine) -> None:
    """[platform/database-schema] 마이그레이션으로 스키마 생성 / 빈 DB에 upgrade

    conftest의 migrated_db가 base로 내린 뒤 head까지 올린 DB다.
    """
    assert await _table_names(engine) == ALL_TABLES
    assert len(ALL_TABLES) == 11


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
