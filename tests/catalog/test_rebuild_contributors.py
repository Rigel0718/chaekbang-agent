"""[catalog/book-contributors] 기여자와 저자 키 다시 만들기 (scripts/rebuild_contributors.py)."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Tenant
from tests.helpers import add_book, add_library_book, fetch, make_isbn

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "rebuild_contributors.py"
_spec = importlib.util.spec_from_file_location("rebuild_contributors", SCRIPT)
assert _spec and _spec.loader
rebuild = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rebuild)


async def _stale(session: AsyncSession, library_id: int) -> tuple[list, list]:
    """기여자가 없는 공식 서지 3건, 저자 키가 빈 기관 도서 5건(마이그레이션 직후와 같은 상태)."""
    books = [
        await add_book(session, make_isbn(300 + i), author=f"작가{i} 저/역자{i} 역")
        for i in range(3)
    ]
    library_books = [
        await add_library_book(
            session,
            library_id,
            None,
            title=f"책{i}",
            author=f"김주민{i} 지음",
            kdc="813",
            author_keys=[],
        )
        for i in range(5)
    ]
    return books, library_books


async def _count(session: AsyncSession, table: str) -> int:
    return await session.scalar(text(f"SELECT count(*) FROM {table}"))


async def test_first_fill(
    session: AsyncSession, library_a: Tenant, capsys: pytest.CaptureFixture[str]
) -> None:
    """[catalog/book-contributors] 기여자와 저자 키 다시 만들기 / 처음 채우기"""
    books, library_books = await _stale(session, library_a.id)
    assert await rebuild.execute(session, check=False) == 0
    out = capsys.readouterr().out
    assert "공식 서지 기여자: 고침 3건" in out
    assert "기관 도서 저자 키: 고침 5건" in out
    assert await _count(session, "book_contributors") == 6
    for i, book in enumerate(library_books):
        assert (await fetch(session, "library_books", book["id"]))["author_keys"] == [f"김주민{i}"]


async def test_rerun_changes_nothing(
    session: AsyncSession, library_a: Tenant, capsys: pytest.CaptureFixture[str]
) -> None:
    """[catalog/book-contributors] 기여자와 저자 키 다시 만들기 / 다시 실행"""
    await _stale(session, library_a.id)
    await rebuild.execute(session, check=False)
    before = (
        (await session.execute(text("SELECT * FROM book_contributors ORDER BY id")))
        .mappings()
        .all()
    )
    capsys.readouterr()
    assert await rebuild.execute(session, check=False) == 0
    out = capsys.readouterr().out
    assert "공식 서지 기여자: 고침 0건" in out and "기관 도서 저자 키: 고침 0건" in out
    after = (
        (await session.execute(text("SELECT * FROM book_contributors ORDER BY id")))
        .mappings()
        .all()
    )
    assert before == after


async def test_check_mode_writes_nothing(
    session: AsyncSession, library_a: Tenant, capsys: pytest.CaptureFixture[str]
) -> None:
    """[catalog/book-contributors] 기여자와 저자 키 다시 만들기 / 확인 방식"""
    await add_library_book(session, library_a.id, None, title="가", author="박마을", author_keys=[])
    await add_library_book(
        session, library_a.id, None, title="나", author="김주민", author_keys=["x"]
    )
    await add_library_book(session, library_a.id, None, title="다", author="이미 맞음")
    await add_library_book(session, library_a.id, None, title="라", author="a", kdc="KDC 813")
    assert await rebuild.execute(session, check=True) == 0
    out = capsys.readouterr().out
    assert "기관 도서 저자 키: 다름 2건" in out
    assert "맞춰지지 않은 분류기호: 1건" in out
    keys = set(
        await session.scalars(text("SELECT array_to_string(author_keys, ',') FROM library_books"))
    )
    assert keys == {"", "x", "이미맞음", "a"}


async def test_institution_values_kept(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-contributors] 기여자와 저자 키 다시 만들기 / 기관의 값은 그대로"""
    _, library_books = await _stale(session, library_a.id)
    odd = await add_library_book(
        session,
        library_a.id,
        None,
        title=" 서명 ",
        author="김 주민 지음",
        kdc="KDC 813.7",
        author_keys=[],
    )
    before = [await fetch(session, "library_books", b["id"]) for b in [*library_books, odd]]
    await rebuild.execute(session, check=False)
    for row in before:
        after = await fetch(session, "library_books", row["id"])
        assert (after["title"], after["author"], after["kdc"]) == (
            row["title"],
            row["author"],
            row["kdc"],
        )


async def test_stale_migration(
    session: AsyncSession, library_a: Tenant, capsys: pytest.CaptureFixture[str]
) -> None:
    """[catalog/book-contributors] 기여자와 저자 키 다시 만들기 / 마이그레이션 전 실행"""
    _, library_books = await _stale(session, library_a.id)
    await session.execute(text("UPDATE alembic_version SET version_num = 'old'"))
    assert await rebuild.execute(session, check=False) == 1
    assert "alembic upgrade head" in capsys.readouterr().err
    assert await _count(session, "book_contributors") == 0
    assert (await fetch(session, "library_books", library_books[0]["id"]))["author_keys"] == []


def test_arguments(capsys: pytest.CaptureFixture[str]) -> None:
    assert rebuild.parse_args([]).check is False
    assert rebuild.parse_args(["--check"]).check is True
    with pytest.raises(SystemExit) as exc:
        rebuild.parse_args(["--full"])
    assert exc.value.code == 1
