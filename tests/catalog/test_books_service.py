"""도서 service 단위 테스트 (catalog/books)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.catalog import BookCreate, BookUpdate
from app.services.catalog import books
from app.services.errors import ConflictError, NotFoundError
from tests.helpers import VALID_ISBN, VALID_ISBN_2, insert


def _create(isbn: str = VALID_ISBN, **overrides) -> BookCreate:
    data = {"isbn": isbn, "title": "모모", "author": "미하엘 엔데", "list_price": 13000}
    data.update(overrides)
    return BookCreate(**data)


async def test_create_and_get(session: AsyncSession) -> None:
    """[catalog/books] 도서 등록 / 정상 등록"""
    created = await books.create_book(session, _create(isbn="978-0-306-40615-7"))
    assert created.isbn == VALID_ISBN
    fetched = await books.get_book(session, VALID_ISBN)
    assert fetched.title == "모모"
    assert fetched.created_at is not None


async def test_create_duplicate_raises_conflict(session: AsyncSession) -> None:
    """[catalog/books] ISBN 중복 금지 / 중복 등록"""
    await books.create_book(session, _create())
    with pytest.raises(ConflictError):
        await books.create_book(session, _create(title="다른 제목"))
    assert (await books.get_book(session, VALID_ISBN)).title == "모모"


async def test_get_missing_raises_not_found(session: AsyncSession) -> None:
    """[catalog/books] 도서 조회 / 없는 도서 조회"""
    with pytest.raises(NotFoundError):
        await books.get_book(session, VALID_ISBN)


async def test_list_returns_page_and_total(session: AsyncSession) -> None:
    """[catalog/books] 도서 조회 / 목록 페이지네이션"""
    await books.create_book(session, _create(VALID_ISBN, title="나"))
    await books.create_book(session, _create(VALID_ISBN_2, title="가"))
    items, total = await books.list_books(session, limit=1, offset=0)
    assert total == 2
    assert [b.title for b in items] == ["가"]


async def test_update_changes_only_given_fields(session: AsyncSession) -> None:
    """[catalog/books] 도서 수정 / 정가 수정"""
    await books.create_book(session, _create(publisher="비룡소"))
    updated = await books.update_book(session, VALID_ISBN, BookUpdate(list_price=14000))
    assert updated.list_price == 14000
    assert updated.publisher == "비룡소"
    assert updated.title == "모모"


async def test_delete_with_inventory_raises_conflict(session: AsyncSession) -> None:
    """[catalog/books] 도서 삭제 / 재고가 있는 도서 삭제"""
    await books.create_book(session, _create())
    await insert(session, "store_inventory", isbn=VALID_ISBN, quantity=1)
    with pytest.raises(ConflictError, match="재고"):
        await books.delete_book(session, VALID_ISBN)


async def test_delete_referenced_by_other_context_raises_conflict(session: AsyncSession) -> None:
    """[catalog/books] 도서 삭제 / 다른 컨텍스트가 참조하는 도서 삭제"""
    await books.create_book(session, _create())
    await insert(session, "quotes", text="글귀", isbn=VALID_ISBN)
    with pytest.raises(ConflictError, match="참조"):
        await books.delete_book(session, VALID_ISBN)
    assert await books.get_book(session, VALID_ISBN)
