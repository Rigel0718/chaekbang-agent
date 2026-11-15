"""platform/database-schema 스펙 테스트."""

import asyncio
import unicodedata
import uuid
from datetime import date, time

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.core import clock
from app.core.migrations import alembic_config
from app.core.text import JAMO_FUNCTION, jamo_starts
from app.models import SHARED_TABLES, TENANT_TABLES, Base
from tests.conftest import Tenant
from tests.helpers import (
    add_book,
    add_holding,
    add_library_book,
    add_member,
    assert_rejected,
    assert_sql_rejected,
    insert,
    make_isbn,
)

ALL_TABLES = {
    "libraries",
    "staff_users",
    "staff_sessions",
    "books",
    "book_contributors",
    "library_books",
    "library_book_audiences",
    "holdings",
    "holding_imports",
    "members",
    "loans",
    "agent_runs",
    "agent_steps",
    "chat_sessions",
    "chat_messages",
    "recommendation_events",
    "library_guides",
    "library_opening_hours",
    "library_closures",
    "library_guide_entries",
    "book_embeddings",
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
    assert len(ALL_TABLES) == 21
    async with engine.connect() as conn:
        extensions = set(await conn.scalars(text("select extname from pg_extension")))
        functions = set(await conn.scalars(text("select proname from pg_proc")))
    assert "fuzzystrmatch" in extensions
    assert "vector" in extensions
    assert JAMO_FUNCTION in functions


async def test_lookup_keys_follow_title(session: AsyncSession, library_a: Tenant) -> None:
    """[platform/database-schema] 마이그레이션으로 스키마 생성 / 찾기 키 열의 자동 계산"""
    book = await add_library_book(session, library_a.id, None, title="데미안", author="헤세")
    assert book["title_jamo_starts"] == jamo_starts("데미안")
    await session.execute(
        text("UPDATE library_books SET title = '최소한의 한국사' WHERE id = :id"),
        {"id": book["id"]},
    )
    changed = await session.scalar(
        text("SELECT title_jamo_starts FROM library_books WHERE id = :id"), {"id": book["id"]}
    )
    assert changed == jamo_starts("최소한의 한국사")
    official = await add_book(session, make_isbn(77), title="싯다르타", author="헤르만 헤세")
    assert official["author_jamo_starts"] == jamo_starts("헤르만 헤세")


async def test_chat_messages_note_column(engine: AsyncEngine) -> None:
    """[platform/database-schema] 마이그레이션으로 스키마 생성 / 대화 메시지의 책 표시 칸"""

    def columns(sync_conn):
        return {c["name"]: c for c in inspect(sync_conn).get_columns("chat_messages")}

    async with engine.connect() as conn:
        found = await conn.run_sync(columns)
    assert found["note"]["nullable"] is True


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


async def test_holding_rejects_library_book_of_other_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[platform/database-schema] 기관 간 참조 금지 / 다른 기관 도서로 사본 직접 저장"""
    theirs = await add_library_book(session, library_b.id)
    await assert_rejected(
        session,
        "holdings",
        library_id=library_a.id,
        library_book_id=theirs["id"],
        accession_number="A-1",
        acquisition_type="donated",
        match="fk_holdings_library_id_library_book_id",
    )


async def test_audience_rejects_library_book_of_other_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[platform/database-schema] 기관 간 참조 금지 / 다른 기관 도서로 어린이 구분 직접 저장"""
    theirs = await add_library_book(session, library_b.id)
    await assert_rejected(
        session,
        "library_book_audiences",
        library_id=library_a.id,
        library_book_id=theirs["id"],
        audience="children",
        audience_source="manual",
        match="fk_library_book_audiences_library_id_library_book_id",
    )


async def test_loan_rejects_holding_of_other_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[platform/database-schema] 기관 간 참조 금지 / 다른 기관 사본으로 대출 직접 저장"""
    book = await add_library_book(session, library_b.id)
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
    book = await add_library_book(session, library_a.id)
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


async def test_step_rejects_run_of_other_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[platform/database-schema] 기관 간 참조 금지 / 다른 기관 실행으로 단계 직접 저장"""
    run_b = await insert(
        session,
        "agent_runs",
        library_id=library_b.id,
        profile="p",
        profile_version="v1",
        model="m",
        started_at=clock.now(),
    )
    await assert_rejected(
        session,
        "agent_steps",
        library_id=library_a.id,
        run_id=run_b["id"],
        seq=1,
        kind="llm",
        duration_ms=1,
        match="fk_agent_steps_library_id_run_id_agent_runs",
    )


async def _run(session: AsyncSession, library_id: int):
    return await insert(
        session,
        "agent_runs",
        library_id=library_id,
        profile="p",
        profile_version="v1",
        model="m",
        started_at=clock.now(),
    )


async def test_message_rejects_session_of_other_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[platform/database-schema] 기관 간 참조 금지 / 다른 기관 세션으로 메시지 직접 저장"""
    chat_b = await insert(
        session,
        "chat_sessions",
        id=uuid.uuid4(),
        library_id=library_b.id,
        last_active_at=clock.now(),
    )
    await assert_rejected(
        session,
        "chat_messages",
        library_id=library_a.id,
        session_id=chat_b["id"],
        role="user",
        content="공룡 책",
        match="fk_chat_messages_library_id_session_id_chat_sessions",
    )


async def test_event_rejects_library_book_of_other_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[platform/database-schema] 기관 간 참조 금지 / 다른 기관 도서로 노출 기록 직접 저장"""
    theirs = await add_library_book(session, library_b.id)
    run_a = await _run(session, library_a.id)
    await assert_rejected(
        session,
        "recommendation_events",
        library_id=library_a.id,
        library_book_id=theirs["id"],
        run_id=run_a["id"],
        position=1,
        was_available=True,
        shown_at=clock.now(),
        match="fk_recommendation_events_library_id_library_book_id",
    )


async def test_event_rejects_run_of_other_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[platform/database-schema] 기관 간 참조 금지 / 다른 기관 실행으로 노출 기록 직접 저장"""
    ours = await add_library_book(session, library_a.id)
    run_b = await _run(session, library_b.id)
    await assert_rejected(
        session,
        "recommendation_events",
        library_id=library_a.id,
        library_book_id=ours["id"],
        run_id=run_b["id"],
        position=1,
        was_available=True,
        shown_at=clock.now(),
        match="fk_recommendation_events_library_id_run_id_agent_runs",
    )


async def test_guide_tables_reject_bad_rows(session: AsyncSession, library_a: Tenant) -> None:
    """[platform/database-schema] 마이그레이션으로 스키마 생성 / 안내 테이블의 저장 계층 규칙"""
    await assert_rejected(
        session,
        "library_opening_hours",
        library_id=library_a.id,
        weekday=1,
        opens_at=time(18),
        closes_at=time(9),
        match="ck_library_opening_hours_opens_before_closes",
    )
    await insert(session, "library_closures", library_id=library_a.id, closed_on=date(2026, 11, 20))
    await assert_rejected(
        session,
        "library_closures",
        library_id=library_a.id,
        closed_on=date(2026, 11, 20),
        match="uq_library_closures_library_id",
    )


_EMBEDDING_INSERT = (
    "INSERT INTO book_embeddings"
    " (library_id, library_book_id, model_name, text_version, embedding, content_hash)"
    " VALUES (:library_id, :library_book_id, :model_name, 1, (:embedding)::text::vector, :hash)"
)


def _vector_text(dim: int) -> str:
    return "[" + ",".join(["0.5"] * dim) + "]"


async def test_embedding_table_rejects_bad_rows(session: AsyncSession, library_a: Tenant) -> None:
    """[platform/database-schema] 마이그레이션으로 스키마 생성 / 임베딩 테이블의 저장 계층 규칙"""
    mine = await add_library_book(session, library_a.id)
    row = {
        "library_id": library_a.id,
        "library_book_id": mine["id"],
        "model_name": "fake",
        "hash": "0" * 64,
    }
    await session.execute(text(_EMBEDDING_INSERT), {**row, "embedding": _vector_text(1024)})
    await assert_sql_rejected(
        session,
        _EMBEDDING_INSERT,
        match="uq_book_embeddings_library_book_model_version",
        **row,
        embedding=_vector_text(1024),
    )
    await assert_sql_rejected(
        session,
        _EMBEDDING_INSERT,
        match="expected 1024 dimensions",
        error=DBAPIError,
        **{**row, "model_name": "other"},
        embedding=_vector_text(3),
    )


async def test_embedding_rejects_library_book_of_other_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[platform/database-schema] 기관 간 참조 금지 / 다른 기관 도서로 임베딩 직접 저장"""
    theirs = await add_library_book(session, library_b.id)
    await assert_sql_rejected(
        session,
        _EMBEDDING_INSERT,
        match="fk_book_embeddings_library_id_library_book_id",
        library_id=library_a.id,
        library_book_id=theirs["id"],
        model_name="fake",
        hash="0" * 64,
        embedding=_vector_text(1024),
    )


# --- add-book-contributors ---

_CONTRIBUTOR_INSERT = (
    "INSERT INTO book_contributors (book_id, position, name, name_key, role) "
    "VALUES (:book_id, :position, :name, :name_key, 'author')"
)


async def test_contributor_table_rejects_bad_rows(session: AsyncSession) -> None:
    """[platform/database-schema] 마이그레이션으로 스키마 생성 / 기여자 테이블의 저장 계층 규칙"""
    book = await add_book(session, make_isbn(81))
    row = {"book_id": book["id"], "position": 0, "name": "김영하", "name_key": "김영하"}
    await session.execute(text(_CONTRIBUTOR_INSERT), row)
    await assert_sql_rejected(
        session, _CONTRIBUTOR_INSERT, match="uq_book_contributors_book_id_position", **row
    )
    await assert_sql_rejected(
        session, _CONTRIBUTOR_INSERT, match="name_not_empty", **{**row, "position": 1, "name": ""}
    )
    await assert_sql_rejected(
        session,
        _CONTRIBUTOR_INSERT,
        match="fk_book_contributors_book_id_books",
        **{**row, "book_id": book["id"] + 100000},
    )


async def test_contributors_deleted_with_book(session: AsyncSession) -> None:
    """[catalog/book-contributors] 공식 서지 기여자 저장 / 공식 서지와 함께 삭제"""
    book = await add_book(session, make_isbn(82))
    await session.execute(
        text(_CONTRIBUTOR_INSERT),
        {"book_id": book["id"], "position": 0, "name": "김영하", "name_key": "김영하"},
    )
    await session.execute(text("DELETE FROM books WHERE id = :id"), {"id": book["id"]})
    left = await session.scalar(
        text("SELECT count(*) FROM book_contributors WHERE book_id = :id"), {"id": book["id"]}
    )
    assert left == 0


async def test_contributor_table_is_shared(engine: AsyncEngine) -> None:
    """[platform/database-schema] 기관 데이터 테이블 구분 / 기여자 테이블은 기관 공통"""

    def columns(sync_conn):
        found = inspect(sync_conn)
        return (
            {c["name"] for c in found.get_columns("book_contributors")},
            {fk["referred_table"] for fk in found.get_foreign_keys("book_contributors")},
        )

    async with engine.connect() as conn:
        names, referred = await conn.run_sync(columns)
    assert "book_contributors" in SHARED_TABLES
    assert "library_id" not in names
    assert referred == {"books"}


async def test_library_book_requires_author_keys(session: AsyncSession, library_a: Tenant) -> None:
    """[platform/database-schema] 마이그레이션으로 스키마 생성 / 저자 키 없는 기관 도서 직접 저장"""
    await assert_rejected(
        session,
        "library_books",
        library_id=library_a.id,
        title="t",
        author="a",
        match="author_keys",
    )
    row = await insert(
        session, "library_books", library_id=library_a.id, title="t", author="a", author_keys=[]
    )
    assert row["author_keys"] == []


async def test_lookup_keys_fullwidth_and_nfd(session: AsyncSession, library_a: Tenant) -> None:
    """[platform/database-schema] 마이그레이션으로 스키마 생성 / 찾기 키 열의 전각·분해형 처리"""
    wide = await add_library_book(session, library_a.id, None, title="ＡＢＣ 살인사건", author="ａ")
    assert wide["title_jamo_starts"] == jamo_starts("ABC 살인사건")
    decomposed = unicodedata.normalize("NFD", "데미안")
    nfd = await add_library_book(session, library_a.id, None, title=decomposed, author="헤세")
    assert nfd["title_jamo_starts"] == jamo_starts("데미안")
