"""[catalog/library-books] 기관 도서 저장 제약과 대상 구분 (DB 직접 쓰기)."""

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Tenant
from tests.helpers import (
    VALID_ISBN,
    add_holding,
    add_library_book,
    assert_rejected,
    assert_sql_rejected,
)


async def test_rejects_malformed_isbn(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/library-books] 기관 도서 저장 제약 / 잘못된 ISBN 직접 저장"""
    values = {"library_id": library_a.id, "title": "t", "author": "a"}
    await assert_rejected(
        session, "library_books", isbn="978-0306406157", error=DBAPIError, **values
    )
    await assert_rejected(
        session, "library_books", isbn="978-030640615", match="isbn_format", **values
    )


async def test_rejects_duplicate_isbn_in_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/library-books] 기관 도서 저장 제약 / 같은 기관의 중복 ISBN 직접 저장

    다른 기관의 같은 ISBN과 ISBN 없는 도서 여러 권은 허용한다.
    """
    await add_library_book(session, library_a.id)
    await assert_rejected(
        session,
        "library_books",
        library_id=library_a.id,
        isbn=VALID_ISBN,
        title="t",
        author="a",
        match="uq_library_books_library_id_isbn",
    )
    await add_library_book(session, library_b.id)
    await add_library_book(session, library_a.id, None)
    await add_library_book(session, library_a.id, None)


async def test_rejects_negative_price(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/library-books] 기관 도서 저장 제약 / 음수 정가 직접 저장 (빈 정가는 허용)"""
    await assert_rejected(
        session,
        "library_books",
        library_id=library_a.id,
        title="t",
        author="a",
        list_price=-1000,
        match="list_price_nonnegative",
    )
    await add_library_book(session, library_a.id, list_price=None)


async def test_rejects_deleting_referenced_library_book(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/library-books] 기관 도서 저장 제약 / 참조된 기관 도서 직접 삭제"""
    book = await add_library_book(session, library_a.id)
    await add_holding(session, library_a.id, book["id"], "A-1")
    await assert_sql_rejected(
        session,
        "DELETE FROM library_books WHERE id = :id",
        id=book["id"],
        match="fk_holdings_library_id_library_book_id",
    )
