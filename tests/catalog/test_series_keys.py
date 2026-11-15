"""[catalog/books] 시리즈 키와 공식 서지를 만드는 함수(`create_official`)."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.external.yes24.parsing import parse_item
from app.central.official_books import create_official, series_keys
from tests.helpers import add_book, make_isbn
from tests.yes24_helpers import item


async def _create(session: AsyncSession, n: int, **values):
    isbn = make_isbn(n)
    return await create_official(session, isbn, parse_item(item(isbn, **values)))


async def test_many_series(session: AsyncSession) -> None:
    """[catalog/books] 시리즈 키 / 시리즈 여러 개"""
    series = [{"seriesName": "민들레그림책"}, {"seriesName": "우리 그림책"}]
    book = await _create(session, 601, series=series)
    assert book.series_keys == ["민들레그림책", "우리그림책"]
    assert book.series_name == "민들레그림책, 우리 그림책"


async def test_series_with_comma(session: AsyncSession) -> None:
    """[catalog/books] 시리즈 키 / 쉼표가 든 시리즈명"""
    book = await _create(session, 602, series=[{"seriesName": "읽고, 쓰고, 생각하고"}])
    assert book.series_keys == ["읽고쓰고생각하고"]


async def test_no_series(session: AsyncSession) -> None:
    """[catalog/books] 시리즈 키 / 시리즈 없음"""
    book = await _create(session, 603, series=None)
    assert book.series_keys == []
    stored = await session.scalar(
        text("SELECT series_keys FROM books WHERE id = :id"), {"id": book.id}
    )
    assert stored == []


async def test_same_series_written_differently(session: AsyncSession) -> None:
    """[catalog/books] 시리즈 키 / 표기가 다른 같은 시리즈"""
    first = await _create(session, 604, series=[{"seriesName": "Why? 과학"}])
    second = await _create(session, 605, series=[{"seriesName": "WHY 과학"}])
    assert set(first.series_keys) & set(second.series_keys) == {"why과학"}


def test_series_keys_skip_blank_and_duplicates() -> None:
    """[catalog/books] 시리즈 키 (빈 키와 중복 제외, 순서 유지)"""
    assert series_keys(["B 시리즈", "...", "a", "b시리즈", "A"]) == ["b시리즈", "a"]


async def test_existing_official_not_changed(session: AsyncSession) -> None:
    """[catalog/books] 공식 서지 쓰기 제한 (이미 있는 공식 서지는 고치지 않는다)"""
    isbn = make_isbn(606)
    existing = await add_book(session, isbn, title="원래 서명")
    book = await create_official(session, isbn, parse_item(item(isbn, title="다른 서명")))
    assert (book.id, book.title, book.series_keys) == (existing["id"], "원래 서명", [])
