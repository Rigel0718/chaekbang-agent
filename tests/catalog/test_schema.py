"""catalog/books 저장 제약 스펙 테스트."""

from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import VALID_ISBN, add_book, assert_rejected, assert_sql_rejected, insert


async def test_rejects_hyphenated_isbn(session: AsyncSession) -> None:
    """[catalog/books] 도서 저장 제약 / 잘못된 ISBN 직접 저장"""
    await assert_rejected(
        session, "books", isbn="978-0306406157", title="t", author="a", list_price=1000
    )
    # 길이 제한이 아니라 형식 CHECK로도 거부되는지 (13자리지만 하이픈 포함)
    await assert_rejected(
        session, "books", isbn="978-030640615", title="t", author="a", list_price=1000
    )


async def test_rejects_negative_list_price(session: AsyncSession) -> None:
    """[catalog/books] 도서 저장 제약 / 음수 정가 직접 저장"""
    await assert_rejected(
        session, "books", isbn=VALID_ISBN, title="t", author="a", list_price=-1000
    )


async def test_rejects_deleting_referenced_book(session: AsyncSession) -> None:
    """[catalog/books] 도서 저장 제약 / 참조된 도서 직접 삭제"""
    await add_book(session)
    await insert(session, "store_inventory", isbn=VALID_ISBN, quantity=1)
    await assert_sql_rejected(session, "DELETE FROM books WHERE isbn = :isbn", isbn=VALID_ISBN)
