"""[catalog/book-contributors] 공식 서지 기여자 저장."""

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.contributors import sync_contributors
from app.central.models import Book, BookContributor
from tests.conftest import Tenant
from tests.helpers import VALID_ISBN, add_holding, add_library_book, make_isbn
from tests.yes24_helpers import FakeYes24, enrich, item, ok


@pytest.fixture
def yes24() -> FakeYes24:
    return FakeYes24()


async def _held(session: AsyncSession, library_id: int, isbn: str = VALID_ISBN) -> None:
    book = await add_library_book(session, library_id, isbn)
    await add_holding(
        session,
        library_id,
        book["id"],
        f"H-{book['id']}",
        acquisition_type="donated",
        purchase_price=None,
    )


async def _contributors(session: AsyncSession, isbn: str = VALID_ISBN) -> list[tuple]:
    rows = await session.execute(
        select(
            BookContributor.position,
            BookContributor.name,
            BookContributor.name_key,
            BookContributor.role,
            BookContributor.role_text,
        )
        .join(Book, Book.id == BookContributor.book_id)
        .where(Book.isbn == isbn)
        .order_by(BookContributor.position)
    )
    return [tuple(r) for r in rows]


async def test_enrichment_stores_contributors(
    session: AsyncSession, yes24: FakeYes24, library_a: Tenant
) -> None:
    """[catalog/book-contributors] 공식 서지 기여자 저장 / 채움 실행"""
    await _held(session, library_a.id)
    yes24.responses[VALID_ISBN] = ok(item(VALID_ISBN, author="앤디 위어 저/박아람 역"))
    await enrich(session, yes24.client())
    author = await session.scalar(
        text("SELECT author FROM books WHERE isbn = :i"), {"i": VALID_ISBN}
    )
    assert author == "앤디 위어 저/박아람 역"
    assert await _contributors(session) == [
        (0, "앤디 위어", "앤디위어", "author", "저"),
        (1, "박아람", "박아람", "translator", "역"),
    ]


async def test_contributor_name_key(
    session: AsyncSession, yes24: FakeYes24, library_a: Tenant
) -> None:
    """[catalog/book-contributors] 공식 서지 기여자 저장 / 이름 맞춤 키"""
    await _held(session, library_a.id)
    yes24.responses[VALID_ISBN] = ok(item(VALID_ISBN, author="J.K. Rowling 저"))
    await enrich(session, yes24.client())
    assert await _contributors(session) == [(0, "J.K. Rowling", "jkrowling", "author", "저")]


async def test_sync_writes_only_when_changed(session: AsyncSession) -> None:
    """같은 원문으로 다시 부르면 쓰지 않는다. 원문이 바뀌면 다시 맞춘다."""
    book = Book(isbn=make_isbn(91), title="t", author="김영하 저")
    session.add(book)
    await session.flush()
    assert await sync_contributors(session, book) is True
    assert await sync_contributors(session, book) is False
    book.author = "김영하 저/홍길동 그림"
    await session.flush()
    assert await sync_contributors(session, book) is True
    assert [r[1] for r in await _contributors(session, make_isbn(91))] == ["김영하", "홍길동"]


async def test_source_without_parser_uses_general_rules(session: AsyncSession) -> None:
    """출처가 없는 공식 서지(시드 등)는 기관 파일 해석기로 읽는다."""
    book = Book(isbn=make_isbn(92), title="t", author="지은이: 한강; 옮긴이: 데보라 스미스")
    session.add(book)
    await session.flush()
    await sync_contributors(session, book)
    rows = await _contributors(session, make_isbn(92))
    assert [(r[1], r[3]) for r in rows] == [("한강", "author"), ("데보라 스미스", "translator")]
