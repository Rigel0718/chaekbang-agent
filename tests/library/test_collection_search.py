"""[catalog/collection-search] 소장 도서 후보 검색."""

from datetime import timedelta
from itertools import count

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.errors import NotFoundError
from app.library.models.catalog import LibraryBook
from app.library.recommendation.search import (
    get_candidate,
    recommendable_ids,
    search_collection,
)
from tests.conftest import Tenant
from tests.helpers import add_book, add_holding, add_library_book, make_isbn

_numbers = count(1)


async def add_held_book(
    session: AsyncSession,
    library_id: int,
    *statuses: str,
    isbn: str | None = None,
    official: dict | None = None,
    synced: list | None = None,
    **values,
):
    """기관 도서와 상태별 사본을 만든다. official을 주면 공식 서지를 만들어 연결한다."""
    book_id = None
    if official is not None:
        isbn = isbn or make_isbn(next(_numbers) + 500)
        book = await add_book(session, isbn, **{"title": values.get("title", "공식"), **official})
        book_id = book["id"]
    values.setdefault("title", "테스트 도서")
    library_book = await add_library_book(session, library_id, isbn, book_id=book_id, **values)
    for i, status in enumerate(statuses or ("available",)):
        extra = {}
        if synced is not None:
            extra["last_synced_at"] = synced[i]
        await add_holding(
            session,
            library_id,
            library_book["id"],
            f"AC{next(_numbers):05d}",
            status=status,
            **extra,
        )
    return library_book


async def _ids(session: AsyncSession, library_id: int, keywords, **kw) -> list[int]:
    return [c.library_book.id for c in await search_collection(session, library_id, keywords, **kw)]


# --- 추천 가능한 책 ---


async def test_on_loan_only_is_found(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/collection-search] 추천 가능한 책 / 대출 중 사본만 있음"""
    book = await add_held_book(session, library_a.id, "on_loan", "on_loan", title="공룡 백과")
    [found] = await search_collection(session, library_a.id, ["공룡"])
    assert found.library_book.id == book["id"]
    assert (found.available_count, found.on_loan_count) == (0, 2)


async def test_lost_only_is_excluded(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/collection-search] 추천 가능한 책 / 분실 사본만 있음"""
    await add_held_book(session, library_a.id, "lost", title="공룡 백과")
    await add_held_book(session, library_a.id, "damaged", "lost", title="공룡 도감")
    assert await _ids(session, library_a.id, ["공룡"]) == []


async def test_withdrawn_only_is_excluded(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/collection-search] 추천 가능한 책 / 제적 사본만 있음"""
    await add_held_book(session, library_a.id, "withdrawn", title="공룡 백과")
    await add_library_book(session, library_a.id, None, title="사본 없는 공룡")
    assert await _ids(session, library_a.id, ["공룡"]) == []
    assert list(await session.scalars(recommendable_ids(library_a.id))) == []


# --- 키워드 검색 ---


async def test_official_description(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/collection-search] 키워드 검색 / 공식 서지의 소개로 찾기"""
    book = await add_held_book(
        session,
        library_a.id,
        title="밤의 박물관",
        official={"title": "밤의 박물관", "description": "공룡 뼈가 살아나는 밤"},
    )
    assert await _ids(session, library_a.id, ["공룡"]) == [book["id"]]


async def test_author_substring(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/collection-search] 키워드 검색 / 저자 원문 일부로 찾기"""
    book = await add_held_book(
        session,
        library_a.id,
        title="프로젝트 헤일메리",
        official={"title": "프로젝트 헤일메리", "author": "앤디 위어 저/박아람 역"},
    )
    assert await _ids(session, library_a.id, ["앤디 위어"]) == [book["id"]]


async def test_without_official(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/collection-search] 키워드 검색 / 공식 서지 없는 책"""
    book = await add_held_book(session, library_a.id, title="마을 공룡 이야기")
    assert await _ids(session, library_a.id, ["공룡"]) == [book["id"]]


async def test_spacing(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/collection-search] 키워드 검색 / 띄어쓰기 차이"""
    book = await add_held_book(session, library_a.id, title="공룡 백과")
    assert await _ids(session, library_a.id, ["공룡백과"]) == [book["id"]]
    assert await _ids(session, library_a.id, ["공룡 백 과"]) == [book["id"]]


async def test_case_insensitive(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/collection-search] 키워드 검색 / 대소문자 구분 없음"""
    book = await add_held_book(session, library_a.id, title="Dinosaur Atlas")
    assert await _ids(session, library_a.id, ["dinosaur"]) == [book["id"]]


async def test_special_characters(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/collection-search] 키워드 검색 / 특수 문자"""
    hit = await add_held_book(session, library_a.id, title="100% 즐기는 여행")
    await add_held_book(session, library_a.id, title="1000가지 요리")
    await add_held_book(session, library_a.id, title="100_퀴즈")
    assert await _ids(session, library_a.id, ["100%"]) == [hit["id"]]
    under = await _ids(session, library_a.id, ["0_"])
    assert len(under) == 1


async def test_subtitle_and_series(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/collection-search] 키워드 검색 / 부제와 시리즈명"""
    sub = await add_held_book(
        session, library_a.id, title="가", official={"title": "가", "subtitle": "공룡의 시대"}
    )
    series = await add_held_book(
        session, library_a.id, title="나", official={"title": "나", "series_name": "공룡 탐험대"}
    )
    assert set(await _ids(session, library_a.id, ["공룡"])) == {sub["id"], series["id"]}


# --- 결과 순서와 개수 ---


async def test_title_before_description(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/collection-search] 결과 순서와 개수 / 서명이 소개보다 앞"""
    desc = await add_held_book(
        session, library_a.id, title="가나다", description="공룡이 나오는 이야기"
    )
    title = await add_held_book(session, library_a.id, title="하하 공룡")
    assert await _ids(session, library_a.id, ["공룡"]) == [title["id"], desc["id"]]


async def test_available_first(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/collection-search] 결과 순서와 개수 / 대출 가능한 책이 앞"""
    on_loan = await add_held_book(session, library_a.id, "on_loan", title="가 공룡")
    available = await add_held_book(session, library_a.id, "available", title="하 공룡")
    assert await _ids(session, library_a.id, ["공룡"]) == [available["id"], on_loan["id"]]


async def test_keyword_scores_add_up(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/collection-search] 결과 순서와 개수 / 키워드별 가중치 합"""
    one = await add_held_book(session, library_a.id, title="가 공룡")
    both = await add_held_book(session, library_a.id, title="하 공룡", description="화석 이야기")
    assert await _ids(session, library_a.id, ["공룡", "화석"]) == [both["id"], one["id"]]


async def test_limit(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/collection-search] 결과 순서와 개수 / 개수 제한"""
    for i in range(11):
        await add_held_book(session, library_a.id, title=f"공룡 {i:02d}")
    assert len(await _ids(session, library_a.id, ["공룡"])) == 10
    assert len(await _ids(session, library_a.id, ["공룡"], limit=50)) == 10


# --- 둘러보기, 범위 ---


async def test_browse_without_keywords(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/collection-search] 키워드 없는 둘러보기 / 키워드 없음"""
    on_loan = await add_held_book(session, library_a.id, "on_loan", title="가")
    available = await add_held_book(session, library_a.id, title="하")
    await add_held_book(session, library_a.id, "lost", title="나")
    assert await _ids(session, library_a.id, []) == [available["id"], on_loan["id"]]
    assert await _ids(session, library_a.id, ["  "]) == [available["id"], on_loan["id"]]


async def test_within(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/collection-search] 검색 범위 좁히기 / 조건 적용"""
    keep = await add_held_book(session, library_a.id, title="공룡 가")
    await add_held_book(session, library_a.id, title="공룡 나")
    within = select(LibraryBook.id).where(LibraryBook.id == keep["id"])
    assert await _ids(session, library_a.id, ["공룡"], within=within) == [keep["id"]]


async def test_other_library_excluded(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/collection-search] 검색의 기관 범위 / 다른 기관 도서 제외"""
    await add_held_book(session, library_b.id, title="공룡 백과")
    assert await _ids(session, library_a.id, ["공룡"]) == []
    assert await _ids(session, library_a.id, []) == []


# --- 대출 상태 시각 ---


async def test_imported_synced_at(session: AsyncSession, library_b: Tenant) -> None:
    """[catalog/collection-search] 대출 상태 시각 / 가져오기 기관"""
    old = clock.now() - timedelta(days=3)
    new = clock.now() - timedelta(hours=1)
    await add_held_book(
        session, library_b.id, "available", "on_loan", title="공룡", synced=[new, old]
    )
    [found] = await search_collection(session, library_b.id, ["공룡"])
    assert found.status_synced_at == old


async def test_imported_synced_missing(session: AsyncSession, library_b: Tenant) -> None:
    """[catalog/collection-search] 대출 상태 시각 / 시각 없는 사본이 있으면 비어 있음"""
    await add_held_book(
        session, library_b.id, "available", "available", title="공룡", synced=[clock.now(), None]
    )
    [found] = await search_collection(session, library_b.id, ["공룡"])
    assert found.status_synced_at is None


async def test_internal_synced_empty(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/collection-search] 대출 상태 시각 / 자체 대출 기관"""
    await add_held_book(session, library_a.id, title="공룡", synced=[clock.now()])
    [found] = await search_collection(session, library_a.id, ["공룡"])
    assert found.status_synced_at is None


async def test_get_candidate_other_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/collection-search] 검색의 기관 범위 / 상세 조회도 기관 범위"""
    book = await add_held_book(session, library_b.id, title="공룡")
    with pytest.raises(NotFoundError):
        await get_candidate(session, library_a.id, book["id"])


async def test_nbsp_in_title(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/collection-search] 키워드 검색 / 띄어쓰기 차이 (줄바꿈 없는 공백)

    PostgreSQL의 `\\s`는 U+00A0을 공백으로 보지 않아 예전 규칙으로는 찾지 못했다.
    """
    book = await add_held_book(session, library_a.id, title="공룡 백과")
    assert await _ids(session, library_a.id, ["공룡백과"]) == [book["id"]]
    assert await _ids(session, library_a.id, ["공룡 백과"]) == [book["id"]]
