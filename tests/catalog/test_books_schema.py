"""[catalog/books] 공식 서지 저장 제약과 쓰기 제한."""

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Tenant
from tests.helpers import (
    VALID_ISBN,
    add_book,
    add_library_book,
    assert_rejected,
    assert_sql_rejected,
    fetch,
)


async def test_rejects_malformed_isbn(session: AsyncSession) -> None:
    """[catalog/books] 도서 저장 제약 / 잘못된 ISBN 직접 저장"""
    # 14자는 CHAR(13) 길이에서, 13자는 CHECK에서 걸린다
    await assert_rejected(
        session, "books", isbn="978-0306406157", title="t", author="a", error=DBAPIError
    )
    await assert_rejected(
        session, "books", isbn="978-030640615", title="t", author="a", match="isbn_format"
    )


async def test_rejects_duplicate_isbn(session: AsyncSession) -> None:
    """[catalog/books] 도서 저장 제약 / 중복 ISBN 직접 저장"""
    await add_book(session)
    await assert_rejected(
        session, "books", isbn=VALID_ISBN, title="t", author="a", match="uq_books_isbn"
    )


async def test_rejects_negative_price(session: AsyncSession) -> None:
    """[catalog/books] 도서 저장 제약 / 음수 정가 직접 저장 (비어 있는 정가는 허용)"""
    await assert_rejected(
        session,
        "books",
        isbn=VALID_ISBN,
        title="t",
        author="a",
        list_price=-1000,
        match="list_price_nonnegative",
    )
    await add_book(session, list_price=None)


async def test_rejects_missing_isbn(session: AsyncSession) -> None:
    """[catalog/books] 도서 저장 제약 / ISBN 없는 행 직접 저장"""
    await assert_rejected(session, "books", title="t", author="a", match="isbn")


async def test_rejects_deleting_referenced_book(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/books] 도서 저장 제약 / 참조된 도서 직접 삭제"""
    book = await add_book(session)
    await add_library_book(session, library_a.id, book_id=book["id"])
    await assert_sql_rejected(
        session, "DELETE FROM books WHERE id = :id", id=book["id"], match="fk_library_books"
    )


@pytest.mark.parametrize(
    ("method", "path"),
    [("POST", "/books"), ("PATCH", "/books/{id}"), ("DELETE", "/books/{id}")],
)
async def test_no_book_write_routes(
    admin_client: AsyncClient, session: AsyncSession, method: str, path: str
) -> None:
    """[catalog/books] 공식 서지 쓰기 제한 / 도서 API 경로 없음"""
    book = await add_book(session, title="공식 서명")
    res = await admin_client.request(
        method,
        path.format(id=book["id"]),
        json={"isbn": VALID_ISBN, "title": "바꿈", "author": "a"},
    )
    assert res.status_code == 404
    assert (await fetch(session, "books", book["id"]))["title"] == "공식 서명"


async def test_library_book_does_not_create_official(
    admin_client: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/books] 공식 서지 쓰기 제한 / 기관 도서 등록은 공식 서지를 만들지 않음"""
    res = await admin_client.post(
        "/library-books", json={"isbn": VALID_ISBN, "title": "t", "author": "a"}
    )
    assert res.status_code == 201
    assert await session.scalar(text("SELECT count(*) FROM books")) == 0
