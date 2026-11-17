"""[catalog/related-recommendation] 비슷한 책 API."""

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.library.recommendation.related import SERIES, SimilarSettings, find_similar
from tests.conftest import Tenant
from tests.library.test_related_books import _product_books
from tests.library.test_related_recommendation import unlinked

FIELDS = {
    "library_book_id",
    "title",
    "author",
    "publisher",
    "available_count",
    "on_loan_count",
    "shelf_location",
    "call_number",
    "cover_url",
    "cover_source",
    "product_url",
    "status_synced_at",
    "basis",
    "basis_text",
}


def _path(library_book_id: int) -> str:
    return f"/catalog/books/{library_book_id}/similar"


async def test_similar_books(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/related-recommendation] 비슷한 책 API / 비슷한 책 조회"""
    ids = await _product_books(session, library_a.id)
    response = await admin_client.get(_path(ids["base"]))
    assert response.status_code == 200
    body = response.json()
    assert 0 < len(body) <= 5
    assert set(body[0]) == FIELDS
    series = next(item for item in body if item["library_book_id"] == ids["series"])
    assert SERIES in series["basis"]
    assert series["basis_text"][0] == "같은 시리즈"


async def test_base_of_other_library(
    admin_client: AsyncClient, session: AsyncSession, library_b: Tenant
) -> None:
    """[catalog/related-recommendation] 비슷한 책 API / 다른 기관의 기준 책"""
    other = await unlinked(session, library_b.id, "남의 책")
    assert (await admin_client.get(_path(other))).status_code == 404


async def test_unrecommendable_base(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/related-recommendation] 비슷한 책 API / 추천할 수 없는 기준 책"""
    gone = await unlinked(session, library_a.id, "제적된 책", "withdrawn")
    assert (await admin_client.get(_path(gone))).status_code == 404


async def test_results_stay_in_library(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/related-recommendation] 비슷한 책 API / 결과의 기관 범위"""
    ids = await _product_books(session, library_a.id)
    theirs = await _product_books(session, library_b.id)
    body = (await admin_client.get(_path(ids["base"]))).json()
    found = {item["library_book_id"] for item in body}
    assert found and not found & set(theirs.values())


async def test_kiosk_account(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/related-recommendation] 비슷한 책 API / 키오스크 계정"""
    ids = await _product_books(session, library_a.id)
    assert (await kiosk_client.get(_path(ids["base"]))).status_code == 200


async def test_no_token(client: AsyncClient) -> None:
    """[catalog/related-recommendation] 비슷한 책 API / 토큰 없음(보조)"""
    assert (await client.get(_path(1))).status_code == 401


async def test_same_as_default_settings(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/related-recommendation] 비슷한 책 API / 기본 설정과 같은 결과"""
    ids = await _product_books(session, library_a.id)
    body = (await kiosk_client.get(_path(ids["base"]))).json()
    plain = await find_similar(
        session,
        get_settings().embedding_model,
        library_id=library_a.id,
        library_book_id=ids["base"],
        settings=SimilarSettings(),
    )
    assert [item["library_book_id"] for item in body] == [r.library_book_id for r in plain]


async def test_leaves_no_records(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/related-recommendation] 비슷한 책 API는 기록하지 않음 / 기록 없음"""
    ids = await _product_books(session, library_a.id)

    async def counts() -> tuple[int, ...]:
        tables = ("agent_runs", "chat_messages", "recommendation_events")
        return tuple([await session.scalar(text(f"select count(*) from {t}")) for t in tables])

    before = await counts()
    assert (await kiosk_client.get(_path(ids["base"]))).status_code == 200
    assert await counts() == before
