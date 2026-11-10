"""[catalog/book-lookup] 검색 API."""

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Tenant
from tests.helpers import add_held_book


async def test_kiosk_search(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/book-lookup] 검색 API / 키오스크 검색"""
    book = await add_held_book(session, library_a.id, "available", "on_loan", title="데미안")
    response = await kiosk_client.get("/catalog/search", params={"q": "데미안"})
    assert response.status_code == 200
    [item] = response.json()
    assert item["library_book_id"] == book["id"]
    assert (item["title"], item["available_count"], item["on_loan_count"]) == ("데미안", 1, 1)
    assert "reason" not in item
    assert {"shelf_location", "call_number", "cover_url", "cover_source", "product_url"} <= set(
        item
    )


async def test_kiosk_suggest(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    book = await add_held_book(session, library_a.id, title="데미안", author="헤르만 헤세")
    response = await kiosk_client.get("/catalog/suggest", params={"q": "데미ㅇ"})
    assert response.status_code == 200
    assert response.json() == [
        {"library_book_id": book["id"], "title": "데미안", "author": "헤르만 헤세"}
    ]


async def test_no_token(client: AsyncClient) -> None:
    """[catalog/book-lookup] 검색 API / 토큰 없음"""
    assert (await client.get("/catalog/suggest", params={"q": "데"})).status_code == 401
    assert (await client.get("/catalog/search", params={"q": "데"})).status_code == 401


@pytest.mark.parametrize("q", ["", "가" * 101])
async def test_query_length(kiosk_client: AsyncClient, q: str) -> None:
    """[catalog/book-lookup] 검색 API / 빈 질의"""
    for path in ("/catalog/search", "/catalog/suggest"):
        assert (await kiosk_client.get(path, params={"q": q})).status_code == 422
    assert (await kiosk_client.get("/catalog/search")).status_code == 422


async def test_library_id_param_ignored(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/book-lookup] 검색 API / 요청의 기관 값 무시"""
    mine = await add_held_book(session, library_a.id, title="공룡 백과")
    await add_held_book(session, library_b.id, title="공룡 도감")
    for path in ("/catalog/search", "/catalog/suggest"):
        response = await kiosk_client.get(path, params={"q": "공룡", "library_id": library_b.id})
        assert [item["library_book_id"] for item in response.json()] == [mine["id"]]


async def test_search_leaves_no_records(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/book-lookup] 검색 기록을 남기지 않음 / 검색 후 기록"""
    await add_held_book(session, library_a.id, title="데미안")

    async def counts() -> tuple[int, ...]:
        tables = ("agent_runs", "chat_messages", "recommendation_events")
        return tuple([await session.scalar(text(f"select count(*) from {t}")) for t in tables])

    before = await counts()
    await kiosk_client.get("/catalog/search", params={"q": "데미안"})
    await kiosk_client.get("/catalog/suggest", params={"q": "데미"})
    assert await counts() == before
