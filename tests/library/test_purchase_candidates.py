"""[library/purchase-requests] 구매 후보: 희망도서, 인기(자체·외부 대출), 분야 숫자, 기관 분리.

오늘은 2026-11-19로 고정한다. 응답 필드는 허용 목록이고 회원 값과 가격은 어디에도 없다.
"""

from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from tests.conftest import Tenant
from tests.helpers import (
    VALID_ISBN,
    VALID_ISBN_2,
    VALID_ISBN_3,
    add_book,
    add_held_book,
    add_holding,
    add_library_book,
    add_loan,
    add_member,
)
from tests.purchase_helpers import add_book_request

URL = "/purchase-requests/candidates"
TODAY = date(2026, 11, 19)
SYNCED = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "today", lambda: TODAY)


async def _get(client: AsyncClient, **params) -> dict:
    res = await client.get(URL, params=params)
    assert res.status_code == 200, res.text
    return res.json()


async def _members(session: AsyncSession, library_id: int, n: int) -> list[dict]:
    return [await add_member(session, library_id, f"M{i:04d}") for i in range(1, n + 1)]


async def _holdings(session: AsyncSession, library_book: dict) -> list[dict]:
    rows = await session.execute(
        text("SELECT id, library_id FROM holdings WHERE library_book_id = :b ORDER BY id"),
        {"b": library_book["id"]},
    )
    return [dict(r) for r in rows.mappings()]


async def _loaned_book(
    session: AsyncSession, library_id: int, member: dict, *, isbn: str | None, loans: int, **values
) -> dict:
    """사본 둘인 책. 한 사본은 반납한 대출 `loans - 1`번, 다른 사본은 대출 중(합쳐 `loans`번)."""
    book = await add_held_book(session, library_id, "available", "available", isbn=isbn, **values)
    first, second = await _holdings(session, book)
    for n in range(loans - 1):
        await add_loan(
            session,
            first,
            member,
            loaned_on=date(2026, 11, 1 + n),
            returned_on=date(2026, 11, 2 + n),
        )
    await add_loan(session, second, member, loaned_on=date(2026, 11, 10))
    return book


# --- 희망도서 후보 ---


async def test_wishes_are_grouped_by_isbn(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/purchase-requests] 구매 후보 / ISBN별 묶기"""
    m1, m2, m3 = await _members(session, library_a.id, 3)
    lib = library_a.id
    await add_book_request(session, lib, member_id=m1["id"], title="A책", isbn=VALID_ISBN)
    await add_book_request(session, lib, member_id=m2["id"], title="A 책", isbn=VALID_ISBN)
    await add_book_request(session, lib, member_id=m3["id"], title="B책", isbn=VALID_ISBN_2)
    body = await _get(admin_client)
    assert [(w["isbn"], w["request_count"]) for w in body["wishes"]] == [
        (VALID_ISBN, 2),
        (VALID_ISBN_2, 1),
    ]
    assert body["wishes"][0]["title"] == "A책"  # 가장 이른 신청의 서명


async def test_wish_for_book_acquired_later_is_dropped(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/purchase-requests] 구매 후보 / 신청 뒤 소장한 책"""
    (member,) = await _members(session, library_a.id, 1)
    lib = library_a.id
    await add_book_request(session, lib, member_id=member["id"], isbn=VALID_ISBN)
    await add_book_request(session, lib, member_id=member["id"], title="다른 책", isbn=VALID_ISBN_2)
    await add_held_book(session, lib, "available", isbn=VALID_ISBN)
    body = await _get(admin_client)
    assert [w["isbn"] for w in body["wishes"]] == [VALID_ISBN_2]


async def test_wish_for_official_isbn_of_held_book_is_dropped(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/purchase-requests] 구매 후보 / 신청 뒤 소장한 책 (공식 서지 ISBN으로 소장)"""
    (member,) = await _members(session, library_a.id, 1)
    await add_book_request(session, library_a.id, member_id=member["id"], isbn=VALID_ISBN_3)
    official = await add_book(session, VALID_ISBN_3)
    held = await add_library_book(session, library_a.id, None, book_id=official["id"])
    await add_holding(session, library_a.id, held["id"], "AC-OFFICIAL", status="available")
    assert (await _get(admin_client))["wishes"] == []


async def test_requests_without_isbn_are_only_counted(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/purchase-requests] 구매 후보 / ISBN 없는 신청"""
    members = await _members(session, library_a.id, 3)
    lib = library_a.id
    for i, member in enumerate(members):
        await add_book_request(session, lib, member_id=member["id"], title=f"무명 {i}")
    await add_book_request(session, lib, member_id=members[0]["id"], title="닫힘", status="closed")
    body = await _get(admin_client)
    assert body["wishes"] == [] and body["wishes_without_isbn"] == 3


async def test_candidates_have_no_member_values_or_price(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/purchase-requests] 구매 후보 / 회원 값 없음 (필드 허용 목록)"""
    member = await add_member(session, library_a.id, "CANARY0001", name="카나리아회원")
    await add_book_request(session, library_a.id, member_id=member["id"], isbn=VALID_ISBN)
    book = await add_held_book(session, library_a.id, "available", isbn=VALID_ISBN_2, title="인기")
    (holding,) = await _holdings(session, book)
    await add_loan(
        session, holding, member, loaned_on=date(2026, 11, 1), returned_on=date(2026, 11, 5)
    )
    res = await admin_client.get(URL)
    assert "카나리아회원" not in res.text and "CANARY0001" not in res.text
    body = res.json()
    assert set(body["wishes"][0]) == {"isbn", "title", "author", "request_count"}
    assert set(body["popular"][0]) == {"isbn", "title", "author", "loans", "copies", "on_loan"}
    assert set(body) == {"basis", "period", "wishes", "wishes_without_isbn", "popular", "fields"}
    assert "price" not in res.text


# --- 인기 후보 ---


async def test_internal_popular_by_loan_count(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/purchase-requests] 인기 후보 / 자체 대출 기관의 인기 후보"""
    (member,) = await _members(session, library_a.id, 1)
    await _loaned_book(session, library_a.id, member, isbn=VALID_ISBN, loans=5, title="가장 인기")
    await _loaned_book(session, library_a.id, member, isbn=VALID_ISBN_2, loans=2, title="그다음")
    body = await _get(admin_client)
    assert body["basis"] == "loan_count"
    assert body["period"]["label"]
    assert body["popular"][0] == {
        "isbn": VALID_ISBN,
        "title": "가장 인기",
        "author": "테스트 저자",
        "loans": 5,
        "copies": 2,
        "on_loan": 1,
    }
    assert [p["isbn"] for p in body["popular"]] == [VALID_ISBN, VALID_ISBN_2]


async def test_popular_period_preset_is_applied(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/purchase-requests] 인기 후보 / 자체 대출 기관의 인기 후보 (기간)"""
    (member,) = await _members(session, library_a.id, 1)
    await _loaned_book(session, library_a.id, member, isbn=VALID_ISBN, loans=3)
    assert (await _get(admin_client, period="last_30_days"))["popular"][0]["loans"] == 3
    assert (await _get(admin_client, period="last_year"))["popular"] == []


async def test_popular_skips_books_without_isbn(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/purchase-requests] 인기 후보 / ISBN 없는 인기 책"""
    (member,) = await _members(session, library_a.id, 1)
    await _loaned_book(session, library_a.id, member, isbn=None, loans=9, title="ISBN 없음")
    await _loaned_book(session, library_a.id, member, isbn=VALID_ISBN, loans=1, title="ISBN 있음")
    body = await _get(admin_client)
    assert [p["title"] for p in body["popular"]] == ["ISBN 있음"]


async def test_external_popular_uses_imported_status(
    admin_client_b: AsyncClient, session: AsyncSession, library_b: Tenant
) -> None:
    """[library/purchase-requests] 인기 후보 / 외부 대출 기관의 인기 후보"""
    await add_held_book(
        session,
        library_b.id,
        "on_loan",
        "on_loan",
        isbn=VALID_ISBN,
        synced=[SYNCED, SYNCED],
        title="모두 대출 중",
    )
    await add_held_book(
        session, library_b.id, "on_loan", "available", isbn=VALID_ISBN_2, synced=[SYNCED] * 2
    )
    await add_held_book(session, library_b.id, "available", isbn=VALID_ISBN_3)
    body = await _get(admin_client_b)
    assert body["basis"] == "imported_status" and body["period"] is None
    first, second = body["popular"]
    assert first["isbn"] == VALID_ISBN and (first["copies"], first["on_loan"]) == (2, 2)
    assert first["synced_at"].startswith("2026-11-18")
    assert "loans" not in first  # 대출 수는 말하지 않는다
    assert (second["copies"], second["on_loan"]) == (2, 1)
    assert len(body["popular"]) == 2  # 대출 중이 없는 책은 없다


async def test_field_figures(
    admin_client: AsyncClient,
    admin_client_b: AsyncClient,
    session: AsyncSession,
    library_a: Tenant,
    library_b: Tenant,
) -> None:
    """[library/purchase-requests] 인기 후보 / 분야별 장서 권수와 권당 대출"""
    (member,) = await _members(session, library_a.id, 1)
    await _loaned_book(session, library_a.id, member, isbn=VALID_ISBN, loans=4, kdc="813.7")
    await add_held_book(
        session, library_b.id, "available", "on_loan", isbn=VALID_ISBN_2, kdc="813.7"
    )
    mine = {f["field"]: f for f in (await _get(admin_client))["fields"]}
    literature = mine["문학"]
    assert (literature["titles"], literature["copies"], literature["loans"]) == (1, 2, 4)
    assert literature["loans_per_copy"] == 2.0
    theirs = {f["field"]: f for f in (await _get(admin_client_b))["fields"]}
    assert theirs["문학"]["copies"] == 2 and theirs["문학"]["loans"] is None


# --- 권한과 기관 분리 ---


async def test_kiosk_cannot_read_candidates(kiosk_client: AsyncClient) -> None:
    """[library/purchase-requests] 요청서 만들기 / 키오스크 (후보)"""
    assert (await kiosk_client.get(URL)).status_code == 403


async def test_candidates_only_from_own_library(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[library/purchase-requests] 구매 후보의 기관 분리 / 다른 기관 목록과 후보"""
    member_a = await add_member(session, library_a.id, "M0001")
    member_b = await add_member(session, library_b.id, "M0001")
    await add_book_request(session, library_a.id, member_id=member_a["id"], isbn=VALID_ISBN)
    await add_book_request(
        session, library_b.id, member_id=member_b["id"], title="B 기관", isbn=VALID_ISBN_2
    )
    await _loaned_book(session, library_b.id, member_b, isbn=VALID_ISBN_3, loans=7, title="B 인기")
    body = await _get(admin_client)
    assert [w["isbn"] for w in body["wishes"]] == [VALID_ISBN]
    assert body["popular"] == []
