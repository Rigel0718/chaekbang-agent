"""[catalog/book-enrichment] 처리 현황과 출처 표시 (기관 API)."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.book_enrichment import run_enrichment
from tests.conftest import Tenant
from tests.helpers import (
    VALID_ISBN,
    VALID_ISBN_2,
    VALID_ISBN_3,
    add_holding,
    add_library_book,
    make_isbn,
)
from tests.yes24_helpers import FakeYes24


async def _held(session: AsyncSession, library_id: int, isbn: str | None, **overrides):
    book = await add_library_book(session, library_id, isbn, **overrides)
    await add_holding(
        session,
        library_id,
        book["id"],
        f"H-{book['id']}",
        acquisition_type="donated",
        purchase_price=None,
    )
    return book


async def test_counts_by_status(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 처리 현황 조회 / 상태별 건수"""
    await _held(session, library_a.id, VALID_ISBN)
    await _held(session, library_a.id, VALID_ISBN_2)
    await _held(session, library_a.id, VALID_ISBN_3, enrichment_status="enriched")
    await _held(session, library_a.id, None)
    await add_library_book(session, library_a.id, make_isbn(1))  # 사본 없음
    res = await admin_client.get("/book-enrichment")
    assert res.status_code == 200
    assert res.json() == {
        "pending": 2,
        "enriched": 1,
        "not_found": 0,
        "mismatch": 0,
        "no_isbn": 1,
    }


async def test_counts_exclude_other_library(
    admin_client: AsyncClient, session: AsyncSession, library_b: Tenant
) -> None:
    """[catalog/book-enrichment] 처리 현황 조회 / 기관 분리"""
    await _held(session, library_b.id, VALID_ISBN)
    body = (await admin_client.get("/book-enrichment")).json()
    assert body["pending"] == 0


async def test_kiosk_rejected(kiosk_client: AsyncClient) -> None:
    """[catalog/book-enrichment] 처리 현황 조회 / 키오스크 계정 거부"""
    assert (await kiosk_client.get("/book-enrichment")).status_code == 403


async def test_no_run_route(admin_client: AsyncClient) -> None:
    """[catalog/book-enrichment] 채움 실행과 대상 / 기관 API 경로 없음"""
    assert (await admin_client.post("/book-enrichment/runs", json={})).status_code == 404


async def test_source_and_link(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 출처 표시 / 출처와 링크"""
    book = await _held(session, library_a.id, VALID_ISBN)
    await run_enrichment(session, FakeYes24().client())
    body = (await admin_client.get(f"/library-books/{book['id']}")).json()
    assert body["external_source"] == "yes24"
    assert body["external_url"] == "https://www.yes24.com/product/goods/15320"


async def test_no_source_without_link(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 출처 표시 / 연결이 없는 도서"""
    book = await _held(session, library_a.id, VALID_ISBN)
    body = (await admin_client.get(f"/library-books/{book['id']}")).json()
    assert (body["external_source"], body["external_url"]) == (None, None)
