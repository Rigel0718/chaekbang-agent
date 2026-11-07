"""[catalog/book-enrichment] 운영자 채움 실행."""

import json

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.external.yes24.client import StopReason
from tests.conftest import Tenant
from tests.helpers import (
    VALID_ISBN,
    VALID_ISBN_2,
    VALID_ISBN_3,
    add_book,
    add_holding,
    add_library_book,
    fetch,
)
from tests.yes24_helpers import FakeYes24, enrich, error, item, ok


@pytest.fixture
def yes24() -> FakeYes24:
    return FakeYes24()


async def _held(session: AsyncSession, library_id: int, isbn: str | None = VALID_ISBN, **overrides):
    """사본이 있는 처리 대기 기관 도서."""
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


async def _status(session: AsyncSession, library_book) -> str:
    return (await fetch(session, "library_books", library_book["id"]))["enrichment_status"]


async def _books(session: AsyncSession) -> int:
    return await session.scalar(text("SELECT count(*) FROM books"))


async def _official(session: AsyncSession, isbn: str = VALID_ISBN):
    result = await session.execute(text("SELECT * FROM books WHERE isbn = :i"), {"i": isbn})
    return result.mappings().one()


# --- 채움 실행과 대상 ---


async def test_processes_held_books(
    session: AsyncSession, yes24: FakeYes24, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 채움 실행과 대상 / 소장 도서 처리"""
    await _held(session, library_a.id)
    await add_library_book(session, library_a.id, VALID_ISBN_2)  # 사본 없음
    await enrich(session, yes24.client())
    assert yes24.isbns == [VALID_ISBN]


async def test_same_isbn_called_once(
    session: AsyncSession, yes24: FakeYes24, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/book-enrichment] 채움 실행과 대상 / 같은 ISBN은 한 번만 조회"""
    ours = await _held(session, library_a.id)
    theirs = await _held(session, library_b.id)
    await enrich(session, yes24.client())
    assert yes24.isbns == [VALID_ISBN]
    assert await _status(session, ours) == await _status(session, theirs) == "enriched"
    assert (await fetch(session, "library_books", theirs["id"]))["book_id"] is not None


async def test_withdrawn_only_excluded(
    session: AsyncSession, yes24: FakeYes24, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 채움 실행과 대상 / 제적 사본만 있는 도서 제외"""
    book = await add_library_book(session, library_a.id)
    await add_holding(session, library_a.id, book["id"], "A-1", status="withdrawn")
    await enrich(session, yes24.client())
    assert yes24.isbns == []


async def test_no_isbn_excluded(session: AsyncSession, yes24: FakeYes24, library_a: Tenant) -> None:
    """[catalog/book-enrichment] 채움 실행과 대상 / ISBN 없는 도서 제외"""
    book = await _held(session, library_a.id, None)
    await enrich(session, yes24.client())
    assert yes24.isbns == []
    assert await _status(session, book) == "pending"


# --- 나눠서 처리 ---


async def _three_pending(session: AsyncSession, library_id: int) -> None:
    for isbn in (VALID_ISBN, VALID_ISBN_2, VALID_ISBN_3):
        await _held(session, library_id, isbn)


async def test_limit(session: AsyncSession, yes24: FakeYes24, library_a: Tenant) -> None:
    """[catalog/book-enrichment] 나눠서 처리 / limit만큼 처리"""
    await _three_pending(session, library_a.id)
    result = await enrich(session, yes24.client(), limit=2)
    assert (result.processed, result.remaining) == (2, 1)


async def test_continues(session: AsyncSession, yes24: FakeYes24, library_a: Tenant) -> None:
    """[catalog/book-enrichment] 나눠서 처리 / 이어서 처리"""
    await _three_pending(session, library_a.id)
    await enrich(session, yes24.client(), limit=2)
    done = list(yes24.isbns)
    await enrich(session, yes24.client(), limit=2)
    assert len(yes24.isbns) == 3 and len(set(yes24.isbns)) == 3
    assert yes24.isbns[:2] == done


# --- 이미 있는 공식 서지 사용 ---


async def test_links_without_call(
    session: AsyncSession, yes24: FakeYes24, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 이미 있는 공식 서지 사용 / 외부 호출 없이 연결"""
    official = await add_book(session)
    book = await _held(session, library_a.id)
    result = await enrich(session, yes24.client())
    assert yes24.isbns == []
    assert result.linked == 1
    row = await fetch(session, "library_books", book["id"])
    assert (row["book_id"], row["enrichment_status"]) == (official["id"], "enriched")
    assert row["enrichment_checked_at"] is not None


# --- 공식 서지 만들기 ---


async def test_creates_official_book(
    session: AsyncSession, yes24: FakeYes24, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 공식 서지 만들기 / 공식 서지 생성"""
    book = await _held(session, library_a.id)
    await enrich(session, yes24.client())
    official = await _official(session)
    assert official["title"] == "강아지똥"
    assert official["publisher"] == "길벗어린이"
    assert official["published_date"].isoformat() == "1996-04-01"
    assert official["list_price"] == 14000
    assert official["description"] == "강아지똥이 민들레 꽃을 피워 내는 이야기"
    assert official["cover_url"] == "https://image.yes24.com/goods/15320/L"
    assert official["external_source"] == "yes24"
    row = await fetch(session, "library_books", book["id"])
    assert (row["book_id"], row["enrichment_status"]) == (official["id"], "enriched")


async def test_library_values_kept(
    session: AsyncSession, yes24: FakeYes24, library_a: Tenant, admin_client: AsyncClient
) -> None:
    """[catalog/book-enrichment] 공식 서지 만들기 / 기관 값 유지"""
    book = await _held(session, library_a.id, title="클린코드")
    yes24.responses[VALID_ISBN] = ok(item(VALID_ISBN, title="클린 코드"))
    await enrich(session, yes24.client())
    assert (await fetch(session, "library_books", book["id"]))["title"] == "클린코드"
    body = (await admin_client.get(f"/library-books/{book['id']}")).json()
    assert body["title"] == "클린 코드"


async def test_author_kept_raw(session: AsyncSession, yes24: FakeYes24, library_a: Tenant) -> None:
    """[catalog/book-enrichment] 공식 서지 만들기 / 저자 원문 보관"""
    await _held(session, library_a.id)
    yes24.responses[VALID_ISBN] = ok(item(VALID_ISBN, author="앤디 위어 저/박아람 역"))
    await enrich(session, yes24.client())
    assert (await _official(session))["author"] == "앤디 위어 저/박아람 역"


async def test_summary_as_description(
    session: AsyncSession, yes24: FakeYes24, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 공식 서지 만들기 / 소개가 없고 줄거리만 있음"""
    await _held(session, library_a.id)
    detail = {"bookIntroduction": None, "bookSummary": "줄거리", "tableOfContents": None}
    yes24.responses[VALID_ISBN] = ok(item(VALID_ISBN, contentDetail=detail))
    await enrich(session, yes24.client())
    assert (await _official(session))["description"] == "줄거리"


async def test_many_series(session: AsyncSession, yes24: FakeYes24, library_a: Tenant) -> None:
    """[catalog/book-enrichment] 공식 서지 만들기 / 시리즈 여러 개"""
    await _held(session, library_a.id)
    series = [{"seriesName": "민들레그림책"}, {"seriesName": "우리그림책"}]
    yes24.responses[VALID_ISBN] = ok(item(VALID_ISBN, series=series))
    await enrich(session, yes24.client())
    assert (await _official(session))["series_name"] == "민들레그림책, 우리그림책"


async def test_extra_fields_in_response(
    session: AsyncSession, yes24: FakeYes24, library_a: Tenant, admin_client: AsyncClient
) -> None:
    """[catalog/book-enrichment] 공식 서지 만들기 / 추가 서지 조회"""
    book = await _held(session, library_a.id)
    detail = {"bookIntroduction": "소개", "bookSummary": None, "tableOfContents": "1장"}
    yes24.responses[VALID_ISBN] = ok(item(VALID_ISBN, subTitle="부제", contentDetail=detail))
    await enrich(session, yes24.client())
    body = (await admin_client.get(f"/library-books/{book['id']}")).json()
    assert (body["subtitle"], body["table_of_contents"]) == ("부제", "1장")
    assert body["series_name"] == "민들레그림책"


async def test_category_kept_raw(
    session: AsyncSession, yes24: FakeYes24, library_a: Tenant, admin_client: AsyncClient
) -> None:
    """[catalog/book-enrichment] 공식 서지 만들기 / 분류 원문 보관"""
    book = await _held(session, library_a.id)
    yes24.responses[VALID_ISBN] = ok(item(VALID_ISBN, goodsSortNm="국내도서-청소년"))
    await enrich(session, yes24.client())
    assert (await _official(session))["external_category"] == "국내도서-청소년"
    body = (await admin_client.get(f"/library-books/{book['id']}")).json()
    assert body["external_category"] == "국내도서-청소년"


async def test_existing_official_not_changed(
    session: AsyncSession, yes24: FakeYes24, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 공식 서지 만들기 (이미 있는 공식 서지는 고치지 않음)"""
    await add_book(session, title="원래 공식 서명")
    await _held(session, library_a.id)
    await enrich(session, yes24.client(), retry_failed=True)
    assert (await _official(session))["title"] == "원래 공식 서명"


# --- 저장하지 않는 값 ---


async def test_volatile_values_not_stored(
    session: AsyncSession, yes24: FakeYes24, library_a: Tenant, admin_client: AsyncClient
) -> None:
    """[catalog/book-enrichment] 저장하지 않는 값 / 변동 정보 미저장"""
    book = await _held(session, library_a.id)
    await enrich(session, yes24.client())
    dump = await session.scalar(text("SELECT json_agg(t)::text FROM books t"))
    body = (await admin_client.get(f"/library-books/{book['id']}")).text
    for value in ("12600", "판매중", "46881", "9.5"):
        assert value not in dump and value not in body
    assert not {"sale_price", "item_status"} & set(json.loads(body))


async def test_cover_image_not_requested(
    session: AsyncSession, yes24: FakeYes24, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 저장하지 않는 값 / 표지 파일 미저장"""
    await _held(session, library_a.id)
    await enrich(session, yes24.client())
    assert [r.url.path for r in yes24.requests] == ["/v1/goods/itemDetail"]
    assert (await _official(session))["cover_url"].startswith("https://")


# --- ISBN 일치 확인 ---


async def test_mismatch(session: AsyncSession, yes24: FakeYes24, library_a: Tenant) -> None:
    """[catalog/book-enrichment] ISBN 일치 확인 / 다른 책 응답"""
    book = await _held(session, library_a.id)
    yes24.responses[VALID_ISBN] = ok(item(VALID_ISBN_2))
    result = await enrich(session, yes24.client())
    assert await _books(session) == 0
    assert await _status(session, book) == "mismatch"
    assert result.mismatch == 1


# --- 찾지 못한 도서 ---


async def test_not_found_continues(
    session: AsyncSession, yes24: FakeYes24, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 찾지 못한 도서 / 상품 없음"""
    first = await _held(session, library_a.id, VALID_ISBN)
    second = await _held(session, library_a.id, VALID_ISBN_2)
    isbns = sorted([VALID_ISBN, VALID_ISBN_2])
    yes24.responses[isbns[0]] = error(404, "GOODS_002")
    await enrich(session, yes24.client())
    assert yes24.isbns == isbns
    statuses = {await _status(session, first), await _status(session, second)}
    assert statuses == {"not_found", "enriched"}


async def test_empty_success_is_not_found(
    session: AsyncSession, yes24: FakeYes24, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 찾지 못한 도서 / 결과가 빈 성공 응답"""
    book = await _held(session, library_a.id)
    yes24.responses[VALID_ISBN] = ok()
    await enrich(session, yes24.client())
    assert await _status(session, book) == "not_found"


@pytest.mark.parametrize(
    "overrides", [{"author": ""}, {"title": ""}, {"author": "가" * 301}, {"title": "가" * 501}]
)
async def test_required_field_missing(
    session: AsyncSession, yes24: FakeYes24, library_a: Tenant, overrides: dict
) -> None:
    """[catalog/book-enrichment] 찾지 못한 도서 / 저자 없는 응답 (길이 초과 포함)"""
    book = await _held(session, library_a.id)
    yes24.responses[VALID_ISBN] = ok(item(VALID_ISBN, **overrides))
    await enrich(session, yes24.client())
    assert await _books(session) == 0
    assert await _status(session, book) == "not_found"


async def test_failed_skipped_by_default(
    session: AsyncSession, yes24: FakeYes24, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 찾지 못한 도서 / 기본 실행에서 제외"""
    await _held(session, library_a.id, enrichment_status="not_found")
    await enrich(session, yes24.client())
    assert yes24.isbns == []


async def test_retry_failed(session: AsyncSession, yes24: FakeYes24, library_a: Tenant) -> None:
    """[catalog/book-enrichment] 찾지 못한 도서 / 다시 시도"""
    book = await _held(session, library_a.id, enrichment_status="not_found")
    mismatch = await _held(session, library_a.id, VALID_ISBN_2, enrichment_status="mismatch")
    await enrich(session, yes24.client(), retry_failed=True)
    assert await _status(session, book) == "enriched"
    assert await _status(session, mismatch) == "enriched"


async def test_retry_failed_after_pending(
    session: AsyncSession, yes24: FakeYes24, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 찾지 못한 도서 (처리 대기 ISBN 뒤에 다시 조회)"""
    await _held(session, library_a.id, VALID_ISBN_2, enrichment_status="not_found")
    await _held(session, library_a.id, VALID_ISBN_3)
    await enrich(session, yes24.client(), limit=1, retry_failed=True)
    assert yes24.isbns == [VALID_ISBN_3]


# --- 외부 장애 시 중단 ---


async def _two_isbns(session: AsyncSession, library_id: int) -> list[str]:
    await _held(session, library_id, VALID_ISBN)
    await _held(session, library_id, VALID_ISBN_2)
    return sorted([VALID_ISBN, VALID_ISBN_2])


async def _statuses(session: AsyncSession) -> dict[str, str]:
    rows = await session.execute(text("SELECT isbn, enrichment_status FROM library_books"))
    return dict(rows.all())


async def test_rate_limited(session: AsyncSession, yes24: FakeYes24, library_a: Tenant) -> None:
    """[catalog/book-enrichment] 외부 장애 시 중단 / 호출 한도 초과"""
    first, second = await _two_isbns(session, library_a.id)
    yes24.responses[second] = httpx.Response(429)
    result = await enrich(session, yes24.client())
    assert result.stopped == StopReason.RATE_LIMITED
    assert await _statuses(session) == {first: "enriched", second: "pending"}
    assert result.remaining == 1


async def test_upstream_unavailable(
    session: AsyncSession, yes24: FakeYes24, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 외부 장애 시 중단 / 외부 서비스 장애"""
    first, second = await _two_isbns(session, library_a.id)
    yes24.responses[first] = error(503, "UPSTREAM_UNAVAILABLE")
    result = await enrich(session, yes24.client())
    assert result.stopped == StopReason.UPSTREAM_UNAVAILABLE
    assert yes24.isbns == [first]
    assert await _statuses(session) == {first: "pending", second: "pending"}


async def test_network_error(session: AsyncSession, yes24: FakeYes24, library_a: Tenant) -> None:
    """[catalog/book-enrichment] 외부 장애 시 중단 / 네트워크 오류"""
    await _held(session, library_a.id)
    yes24.responses[VALID_ISBN] = httpx.ReadTimeout("시간 초과")
    result = await enrich(session, yes24.client())
    assert result.stopped == StopReason.UPSTREAM_UNAVAILABLE


async def test_auth_failed(session: AsyncSession, yes24: FakeYes24, library_a: Tenant) -> None:
    """[catalog/book-enrichment] 외부 장애 시 중단 / 인증 실패"""
    await _held(session, library_a.id)
    yes24.responses[VALID_ISBN] = error(401, "AUTH_002")
    result = await enrich(session, yes24.client())
    assert result.stopped == StopReason.AUTH_FAILED
