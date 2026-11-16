"""[catalog/book-enrichment] 운영자 채움 실행: 정보나루, 카카오, YES24를 조회해 합친다.

채움 실행의 흐름(대상, 나눠서 처리, 연결)은 `test_book_enrichment.py`가 조회 하나로 확인한다.
여기서는 세 출처를 쓰는 실제 조회(`lookup_sources`)로 공식 서지 값과 판단을 본다.
"""

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.contributors import rebuild_contributors
from app.central.external.http import StopReason
from app.central.models import Book, BookContributor
from app.core.contributors import ContributorRole
from tests.conftest import Tenant
from tests.helpers import VALID_ISBN, VALID_ISBN_2, VALID_ISBN_3, add_holding, add_library_book
from tests.helpers import fetch as fetch_row
from tests.source_helpers import (
    FakeSources,
    d4l_book,
    d4l_error,
    d4l_not_found,
    d4l_ok,
    enrich_sources,
    kakao_document,
    kakao_ok,
)
from tests.yes24_helpers import item, ok

YES24_COVER = "https://image.yes24.com/goods/15320/L"
YES24_LINK = "https://www.yes24.com/product/goods/15320"


def _absent(sources: FakeSources, isbn: str, *names: str) -> None:
    """그 출처들이 이 ISBN을 찾지 못한 것으로 둔다."""
    empty = {"data4library": d4l_not_found(), "kakao": kakao_ok(), "yes24": ok()}
    for name in names:
        getattr(sources, name).responses[isbn] = empty[name]


@pytest.fixture
def sources() -> FakeSources:
    return FakeSources()


async def _held(session: AsyncSession, library_id: int, isbn: str = VALID_ISBN, **overrides):
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
    return (await fetch_row(session, "library_books", library_book["id"]))["enrichment_status"]


async def _books(session: AsyncSession) -> int:
    return await session.scalar(text("SELECT count(*) FROM books"))


async def _official(session: AsyncSession, isbn: str = VALID_ISBN):
    result = await session.execute(text("SELECT * FROM books WHERE isbn = :i"), {"i": isbn})
    return result.mappings().one()


async def _contributors(session: AsyncSession, isbn: str = VALID_ISBN) -> list[tuple]:
    rows = await session.execute(
        select(BookContributor.name, BookContributor.role)
        .join(Book, Book.id == BookContributor.book_id)
        .where(Book.isbn == isbn)
        .order_by(BookContributor.position)
    )
    return [tuple(r) for r in rows]


# --- 공식 서지 만들기 ---


async def test_creates_official_from_three_sources(
    session: AsyncSession, sources: FakeSources, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 공식 서지 만들기 / 공식 서지 생성"""
    held = await _held(session, library_a.id)
    result = await enrich_sources(session, sources)
    assert (result.enriched, result.not_found, result.mismatch) == (1, 0, 0)
    assert await _status(session, held) == "enriched"
    book = await _official(session)
    assert (book["title"], book["subtitle"]) == ("강아지똥", None)  # YES24 서명·부제
    assert book["author"] == "권정생 글/정승각 그림"
    assert book["external_source"] == "yes24"
    assert book["list_price"] == 14000
    assert book["addition_symbol"] == "77810"
    assert book["kdc_name"] == "문학 > 한국문학 > 동화"
    assert book["external_category"] == "국내도서-유아"  # YES24 분류 원문
    assert book["description"] == "강아지똥이 민들레 꽃을 피워 내는 이야기"  # YES24 소개
    assert (book["cover_url"], book["external_url"]) == (YES24_COVER, YES24_LINK)
    assert book["field_sources"]["list_price"] == "kakao"
    assert book["field_sources"]["cover_url"] == "yes24"
    assert book["field_sources"]["kdc"] == "data4library"
    # 출처마다 ISBN당 한 번씩 부른다
    assert sources.data4library.isbns == [VALID_ISBN]
    assert sources.kakao.isbns == [VALID_ISBN]
    assert sources.yes24.isbns == [VALID_ISBN]


async def test_same_isbn_called_once_per_source(
    session: AsyncSession, sources: FakeSources, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/book-enrichment] 채움 실행과 대상 / 같은 ISBN은 한 번만 조회"""
    ours = await _held(session, library_a.id)
    theirs = await _held(session, library_b.id)
    await enrich_sources(session, sources)
    assert sources.calls == 3
    assert await _status(session, ours) == await _status(session, theirs) == "enriched"


async def test_existing_official_is_linked_without_calls(
    session: AsyncSession, sources: FakeSources, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 이미 있는 공식 서지 사용 / 외부 호출 없이 연결"""
    await _held(session, library_a.id)
    await enrich_sources(session, sources)
    other = await _held(session, library_a.id, VALID_ISBN_2)
    await session.execute(
        text("INSERT INTO books (isbn, title, author) VALUES (:i, 't', 'a')"), {"i": VALID_ISBN_3}
    )
    late = await _held(session, library_a.id, VALID_ISBN_3)
    calls = sources.calls
    result = await enrich_sources(session, sources)
    assert result.linked == 1
    assert await _status(session, late) == await _status(session, other) == "enriched"
    assert sources.calls == calls + 3  # VALID_ISBN_2만 세 출처를 부른다


async def test_institution_values_kept(
    session: AsyncSession, admin_client: AsyncClient, sources: FakeSources, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 공식 서지 만들기 / 기관 값 유지"""
    held = await _held(session, library_a.id, title="강아지 똥")
    await enrich_sources(session, sources)
    assert (await fetch_row(session, "library_books", held["id"]))["title"] == "강아지 똥"
    body = (await admin_client.get(f"/library-books/{held['id']}")).json()
    assert body["title"] == "강아지똥"


async def test_author_text_is_kept(
    session: AsyncSession, sources: FakeSources, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 공식 서지 만들기 / 저자 원문 보관"""
    await _held(session, library_a.id)
    _absent(sources, VALID_ISBN, "yes24")
    author = "지은이: 히가시노 게이고 ;옮긴이: 양윤옥"
    sources.data4library.responses[VALID_ISBN] = d4l_ok(d4l_book(VALID_ISBN, authors=author))
    await enrich_sources(session, sources)
    assert (await _official(session))["author"] == author


async def test_category_and_kdc_are_kept(
    session: AsyncSession, admin_client: AsyncClient, sources: FakeSources, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 공식 서지 만들기 / 분류 원문 보관"""
    held = await _held(session, library_a.id)
    sources.data4library.responses[VALID_ISBN] = d4l_ok(
        d4l_book(VALID_ISBN, class_no="813.7", class_nm="문학 > 한국문학 > 소설")
    )
    await enrich_sources(session, sources)
    book = await _official(session)
    assert (book["kdc"], book["kdc_name"]) == ("813.7", "문학 > 한국문학 > 소설")
    assert book["external_category"] == "국내도서-유아"
    body = (await admin_client.get(f"/library-books/{held['id']}")).json()
    assert body["external_category"] == "국내도서-유아"
    assert body["kdc"] == "813.7"


async def test_series_from_yes24(
    session: AsyncSession, sources: FakeSources, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 공식 서지 만들기 / 시리즈 여러 개 (YES24)"""
    await _held(session, library_a.id)
    sources.yes24.responses[VALID_ISBN] = ok(
        item(
            VALID_ISBN,
            series=[{"seriesName": "민들레그림책"}, {"seriesName": "우리 그림책"}],
            contentDetail={"tableOfContents": "1. 강아지똥\r\n2. 민들레"},
        )
    )
    await enrich_sources(session, sources)
    book = await _official(session)
    assert book["series_name"] == "민들레그림책, 우리 그림책"
    assert book["series_keys"] == ["민들레그림책", "우리그림책"]
    assert book["table_of_contents"] == "1. 강아지똥\n2. 민들레"
    assert book["field_sources"]["series_name"] == "yes24"


async def test_no_series(session: AsyncSession, sources: FakeSources, library_a: Tenant) -> None:
    """[catalog/book-enrichment] 공식 서지 만들기 / 시리즈 없음"""
    await _held(session, library_a.id)
    _absent(sources, VALID_ISBN, "yes24")
    await enrich_sources(session, sources)
    book = await _official(session)
    assert book["series_name"] is None
    assert book["series_keys"] == []


async def test_subtitle_in_response(
    session: AsyncSession, admin_client: AsyncClient, sources: FakeSources, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 공식 서지 만들기 / 추가 서지 조회"""
    held = await _held(session, library_a.id)
    _absent(sources, VALID_ISBN, "yes24")  # 정보나루 서명에서 나눈 부제
    await enrich_sources(session, sources)
    body = (await admin_client.get(f"/library-books/{held['id']}")).json()
    assert body["subtitle"] == "권정생 그림책"


# --- 저장하지 않는 값 ---


async def test_volatile_values_not_stored(
    session: AsyncSession, admin_client: AsyncClient, sources: FakeSources, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 저장하지 않는 값 / 변동 정보 미저장"""
    held = await _held(session, library_a.id)
    sources.kakao.responses[VALID_ISBN] = kakao_ok(
        kakao_document(VALID_ISBN, sale_price=98765, status="품절임박상태")
    )
    await enrich_sources(session, sources)
    stored = str(dict(await _official(session)))
    body = (await admin_client.get(f"/library-books/{held['id']}")).text
    for value in ("98765", "품절임박상태"):
        assert value not in stored
        assert value not in body


async def test_cover_is_url_only(
    session: AsyncSession, sources: FakeSources, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 저장하지 않는 값 / 표지 파일 미저장"""
    await _held(session, library_a.id)
    await _held(session, library_a.id, VALID_ISBN_2)
    _absent(sources, VALID_ISBN_2, "yes24")
    await enrich_sources(session, sources)
    assert (await _official(session))["cover_url"] == YES24_COVER
    kakao_cover = (await _official(session, VALID_ISBN_2))["cover_url"]
    assert kakao_cover == "https://search1.kakaocdn.net/thumb/cover"
    assert sources.calls == 6  # 이미지 요청은 없다


async def test_data4library_cover_not_stored(
    session: AsyncSession, sources: FakeSources, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 저장하지 않는 값 / 정보나루 표지 미저장"""
    await _held(session, library_a.id)
    _absent(sources, VALID_ISBN, "kakao", "yes24")
    await enrich_sources(session, sources)
    book = await _official(session)
    assert book["cover_url"] is None
    assert "image.example" not in str(dict(book))


# --- ISBN 일치 확인, 찾지 못한 도서 ---


async def test_mismatch(session: AsyncSession, sources: FakeSources, library_a: Tenant) -> None:
    """[catalog/book-enrichment] ISBN 일치 확인 / 다른 책 응답"""
    held = await _held(session, library_a.id)
    _absent(sources, VALID_ISBN, "data4library", "yes24")
    sources.kakao.responses[VALID_ISBN] = kakao_ok(kakao_document(VALID_ISBN_2))
    result = await enrich_sources(session, sources)
    assert result.mismatch == 1
    assert await _books(session) == 0
    assert await _status(session, held) == "mismatch"


async def test_one_source_matches(
    session: AsyncSession, sources: FakeSources, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] ISBN 일치 확인 / 한 출처만 일치"""
    await _held(session, library_a.id)
    _absent(sources, VALID_ISBN, "yes24")
    sources.kakao.responses[VALID_ISBN] = kakao_ok(kakao_document(VALID_ISBN_2, price=99000))
    result = await enrich_sources(session, sources)
    assert result.enriched == 1
    book = await _official(session)
    assert book["external_source"] == "data4library"
    assert book["list_price"] is None


async def test_not_found_in_both(
    session: AsyncSession, sources: FakeSources, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 찾지 못한 도서 / 상품 없음, 결과가 빈 성공 응답"""
    first = await _held(session, library_a.id)
    second = await _held(session, library_a.id, VALID_ISBN_2)
    _absent(sources, VALID_ISBN, "data4library", "kakao", "yes24")
    result = await enrich_sources(session, sources)
    assert (result.not_found, result.enriched) == (1, 1)
    assert await _status(session, first) == "not_found"
    assert await _status(session, second) == "enriched"  # 다음 ISBN을 처리한다


async def test_no_author_in_both(
    session: AsyncSession, sources: FakeSources, library_a: Tenant
) -> None:
    """[catalog/book-enrichment] 찾지 못한 도서 / 저자 없는 응답"""
    held = await _held(session, library_a.id)
    sources.data4library.responses[VALID_ISBN] = d4l_ok(d4l_book(VALID_ISBN, authors=""))
    sources.kakao.responses[VALID_ISBN] = kakao_ok(kakao_document(VALID_ISBN, authors=[]))
    sources.yes24.responses[VALID_ISBN] = ok(item(VALID_ISBN, author=""))
    await enrich_sources(session, sources)
    assert await _books(session) == 0
    assert await _status(session, held) == "not_found"


async def test_retry_failed(session: AsyncSession, sources: FakeSources, library_a: Tenant) -> None:
    """[catalog/book-enrichment] 찾지 못한 도서 / 기본 실행에서 제외, 다시 시도"""
    held = await _held(session, library_a.id)
    _absent(sources, VALID_ISBN, "data4library", "kakao", "yes24")
    await enrich_sources(session, sources)
    calls = sources.calls
    await enrich_sources(session, sources)
    assert sources.calls == calls  # 기본 실행은 다시 부르지 않는다
    del sources.kakao.responses[VALID_ISBN]  # 이번에는 카카오가 찾는다
    await enrich_sources(session, sources, retry_failed=True)
    assert await _status(session, held) == "enriched"
    assert (await _official(session))["external_source"] == "kakao"


# --- 외부 장애 시 중단 ---


@pytest.mark.parametrize(
    ("source", "response", "reason"),
    [
        ("kakao", httpx.Response(429), StopReason.RATE_LIMITED),
        ("data4library", httpx.Response(503), StopReason.UPSTREAM_UNAVAILABLE),
        ("data4library", httpx.ReadTimeout("시간 초과"), StopReason.UPSTREAM_UNAVAILABLE),
        ("kakao", httpx.Response(401), StopReason.AUTH_FAILED),
        ("data4library", d4l_error("일일 호출 한도 초과"), StopReason.RATE_LIMITED),
        ("yes24", httpx.Response(429), StopReason.RATE_LIMITED),
    ],
)
async def test_stops_on_source_failure(
    source: str,
    response,
    reason: StopReason,
    session: AsyncSession,
    sources: FakeSources,
    library_a: Tenant,
) -> None:
    """[catalog/book-enrichment] 외부 장애 시 중단 (한도 초과, 장애, 네트워크 오류, 인증 실패)"""
    # 처리 순서는 ISBN 순서다: VALID_ISBN, VALID_ISBN_3, VALID_ISBN_2
    first = await _held(session, library_a.id, VALID_ISBN)
    second = await _held(session, library_a.id, VALID_ISBN_3)
    third = await _held(session, library_a.id, VALID_ISBN_2)
    getattr(sources, source).responses[VALID_ISBN_3] = response
    result = await enrich_sources(session, sources)
    assert (result.stopped, result.stopped_source) == (reason, source)
    assert result.enriched == 1
    assert await _status(session, first) == "enriched"  # 처리한 결과는 남는다
    assert await _status(session, second) == await _status(session, third) == "pending"
    assert result.remaining == 2


# --- 기여자 ---


async def test_contributors_from_data4library(
    session: AsyncSession, sources: FakeSources, library_a: Tenant
) -> None:
    """[catalog/book-contributors] 출처별 해석기 / 정보나루 이름표 꼴, 정보나루 괄호 꼴"""
    await _held(session, library_a.id)
    await _held(session, library_a.id, VALID_ISBN_2)
    _absent(sources, VALID_ISBN, "yes24")
    _absent(sources, VALID_ISBN_2, "yes24")
    sources.data4library.responses[VALID_ISBN] = d4l_ok(
        d4l_book(VALID_ISBN, authors="지은이: 히가시노 게이고 ;옮긴이: 양윤옥")
    )
    sources.data4library.responses[VALID_ISBN_2] = d4l_ok(
        d4l_book(VALID_ISBN_2, authors="정세랑 (지은이)")
    )
    await enrich_sources(session, sources)
    assert await _contributors(session) == [
        ("히가시노 게이고", ContributorRole.AUTHOR),
        ("양윤옥", ContributorRole.TRANSLATOR),
    ]
    assert await _contributors(session, VALID_ISBN_2) == [("정세랑", ContributorRole.AUTHOR)]


async def test_contributors_from_kakao(
    session: AsyncSession, sources: FakeSources, library_a: Tenant
) -> None:
    """[catalog/book-contributors] 카카오 저자 배열 해석 / 저자 둘과 역자 하나 (공식 서지)"""
    await _held(session, library_a.id)
    _absent(sources, VALID_ISBN, "data4library", "yes24")
    sources.kakao.responses[VALID_ISBN] = kakao_ok(
        kakao_document(VALID_ISBN, authors=["칼 멜링", "브라이트 스타"], translators=["김맑아"])
    )
    await enrich_sources(session, sources)
    assert (await _official(session))["author"] == "칼 멜링, 브라이트 스타 ;옮긴이: 김맑아"
    assert await _contributors(session) == [
        ("칼 멜링", ContributorRole.AUTHOR),
        ("브라이트 스타", ContributorRole.AUTHOR),
        ("김맑아", ContributorRole.TRANSLATOR),
    ]


async def test_rebuild_check_finds_no_difference(
    session: AsyncSession, sources: FakeSources, library_a: Tenant
) -> None:
    """[catalog/book-contributors] 출처별 해석기 / 다시 만들기"""
    await _held(session, library_a.id)
    await _held(session, library_a.id, VALID_ISBN_2)
    await _held(session, library_a.id, VALID_ISBN_3)
    _absent(sources, VALID_ISBN_2, "data4library", "yes24")  # 카카오 출처의 공식 서지
    _absent(sources, VALID_ISBN_3, "data4library")  # YES24 출처의 공식 서지
    await enrich_sources(session, sources)
    assert await rebuild_contributors(session, write=False) == (0, 3)
