"""[catalog/books] 도서 저장 제약과 대상 구분 (DB 직접 쓰기)."""

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Tenant
from tests.helpers import (
    VALID_ISBN,
    add_book,
    add_holding,
    assert_rejected,
    assert_sql_rejected,
)


async def test_rejects_hyphenated_isbn(session: AsyncSession) -> None:
    """[catalog/books] 도서 저장 제약 / 잘못된 ISBN 직접 저장"""
    # 스펙의 예시 값(14자)은 CHAR(13) 길이에서 거부된다
    await assert_rejected(
        session, "books", isbn="978-0306406157", title="t", author="a", error=DBAPIError
    )
    # 13자이지만 하이픈이 섞인 값은 형식 CHECK가 거부한다
    await assert_rejected(
        session, "books", isbn="978-030640615", title="t", author="a", match="isbn_format"
    )


async def test_rejects_duplicate_isbn(session: AsyncSession) -> None:
    """[catalog/books] 도서 저장 제약 / 중복 ISBN 직접 저장 (ISBN 없는 행은 여러 개 허용)"""
    await add_book(session)
    await assert_rejected(
        session, "books", isbn=VALID_ISBN, title="t", author="a", match="uq_books_isbn"
    )
    await add_book(session, None)
    await add_book(session, None)


async def test_rejects_negative_list_price(session: AsyncSession) -> None:
    """[catalog/books] 도서 저장 제약 / 음수 정가 직접 저장 (비어 있는 정가는 허용)"""
    await assert_rejected(
        session,
        "books",
        isbn=VALID_ISBN,
        title="t",
        author="a",
        list_price=-1000,
        match="list_price",
    )
    await add_book(session, list_price=None)


async def test_rejects_deleting_referenced_book(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/books] 도서 저장 제약 / 참조된 도서 직접 삭제"""
    book = await add_book(session)
    await add_holding(session, library_a.id, book["id"], "A-1")
    await assert_sql_rejected(
        session, "DELETE FROM books WHERE id = :id", id=book["id"], match="fk_holdings_book_id"
    )


async def test_rejects_unknown_audience(session: AsyncSession) -> None:
    """[catalog/books] 어린이/일반 도서 구분 / 허용되지 않은 구분"""
    await assert_rejected(
        session, "books", title="t", author="a", audience="teen", match="audience"
    )
