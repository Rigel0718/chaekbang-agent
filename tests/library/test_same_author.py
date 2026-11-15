"""[catalog/book-contributors] 같은 저자 조회."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.contributors import sync_contributors
from app.central.models import Book, ExternalSource
from app.core.errors import NotFoundError
from app.library.recommendation.authors import same_author_books
from tests.conftest import Tenant
from tests.helpers import add_held_book


async def linked(
    session: AsyncSession, library_id: int, official_author: str, *statuses: str, **values
):
    """YES24 공식 서지에 연결된, 사본이 있는 기관 도서. 기여자도 채운다."""
    book = await add_held_book(
        session,
        library_id,
        *statuses,
        official={"author": official_author, "external_source": ExternalSource.YES24.value},
        **values,
    )
    official = await session.scalar(select(Book).where(Book.id == book["book_id"]))
    await sync_contributors(session, official)
    return book


async def unlinked(session: AsyncSession, library_id: int, author: str, *statuses: str, **values):
    return await add_held_book(session, library_id, *statuses, author=author, **values)


async def _ids(session: AsyncSession, library_id: int, book) -> list[int]:
    return [b.id for b in await same_author_books(session, library_id, book["id"])]


async def test_linked_books(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-contributors] 같은 저자 조회 / 연결된 책끼리"""
    base = await linked(session, library_a.id, "헤르만 헤세 저/전영애 역", title="데미안")
    other = await linked(session, library_a.id, "헤르만 헤세 저/박병덕 역", title="싯다르타")
    assert await _ids(session, library_a.id, base) == [other["id"]]


async def test_translator_only(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-contributors] 같은 저자 조회 / 역자만 같은 책"""
    base = await linked(session, library_a.id, "앤 카슨 저/민승남 역", title="빨강의 자서전")
    await linked(session, library_a.id, "존 윌리엄스 저/민승남 역", title="스토너")
    assert await _ids(session, library_a.id, base) == []


async def test_linked_and_unlinked(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-contributors] 같은 저자 조회 / 연결된 책과 연결되지 않은 책"""
    base = await linked(session, library_a.id, "김영하 저", title="검은 꽃")
    other = await unlinked(session, library_a.id, "김 영 하 지음", title="옛 소설")
    assert await _ids(session, library_a.id, base) == [other["id"]]
    assert await _ids(session, library_a.id, other) == [base["id"]]


async def test_linked_uses_official_value(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-contributors] 같은 저자 조회 / 연결된 책은 공식 값

    기관이 저자를 `김연수`로 적어 둔 연결된 책(공식 저자 `김영하 저`)은 김연수의 책으로 보지 않는다.
    """
    misfiled = await linked(session, library_a.id, "김영하 저", title="검은 꽃", author="김연수")
    assert misfiled["author_keys"] == ["김연수"]
    base = await unlinked(session, library_a.id, "김연수 저", title="세계의 끝 여자친구")
    assert await _ids(session, library_a.id, base) == []


async def test_original_author(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-contributors] 같은 저자 조회 / 원저"""
    base = await linked(session, library_a.id, "흔한남매 원저/김언정 글", title="흔한남매 1")
    other = await linked(session, library_a.id, "흔한남매 저", title="흔한남매 일기")
    assert await _ids(session, library_a.id, base) == [other["id"]]


async def test_other_library(session: AsyncSession, library_a: Tenant, library_b: Tenant) -> None:
    """[catalog/book-contributors] 같은 저자 조회 / 다른 기관의 책"""
    base = await unlinked(session, library_a.id, "김영하 지음", title="검은 꽃")
    await unlinked(session, library_b.id, "김영하 지음", title="빛의 제국")
    assert await _ids(session, library_a.id, base) == []


async def test_not_recommendable(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-contributors] 같은 저자 조회 / 추천 가능하지 않은 책"""
    base = await unlinked(session, library_a.id, "김영하 지음", title="검은 꽃")
    await unlinked(session, library_a.id, "김영하 지음", "lost", title="빛의 제국")
    on_loan = await unlinked(session, library_a.id, "김영하", "on_loan", title="퀴즈쇼")
    assert await _ids(session, library_a.id, base) == [on_loan["id"]]


async def test_other_library_base(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/book-contributors] 같은 저자 조회 / 다른 기관의 기준 책"""
    theirs = await unlinked(session, library_b.id, "김영하 지음", title="빛의 제국")
    with pytest.raises(NotFoundError):
        await same_author_books(session, library_a.id, theirs["id"])


async def test_order_by_overlap(session: AsyncSession, library_a: Tenant) -> None:
    """겹치는 지은이가 많은 책이 먼저이고, 같으면 서명 순서다. 지은이가 없는 기준 책은 빈 결과다."""
    base = await unlinked(session, library_a.id, "박마을, 김주민", title="마을 이야기")
    one = await unlinked(session, library_a.id, "김주민", title="가나다")
    both = await unlinked(session, library_a.id, "김주민 / 박마을", title="하하하")
    assert await _ids(session, library_a.id, base) == [both["id"], one["id"]]
    translator = await unlinked(session, library_a.id, "김주민 역", title="옮긴 책")
    assert await _ids(session, library_a.id, translator) == []
