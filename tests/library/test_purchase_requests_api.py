"""[library/purchase-requests] 구매 요청서: 만들기·항목 규칙·승인 흐름·금액·희망도서 닫기·기관 분리.

정가 조회는 가짜 조회기(`FakeListPrices`)로 바꿔 끼우고 YES24는 부르지 않는다. 금액 기대값은
손으로 계산한 상수다(정가 15,000원 × 2권 + 12,000원 × 1권 = 42,000원).
"""

from collections.abc import AsyncIterator

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.library.api.purchase_requests import get_list_prices
from app.main import app
from tests.conftest import Tenant
from tests.helpers import (
    VALID_ISBN,
    VALID_ISBN_2,
    VALID_ISBN_3,
    add_book,
    add_member,
    make_isbn,
)
from tests.purchase_helpers import FakeListPrices, add_book_request, item_body, request_body

URL = "/purchase-requests"


@pytest.fixture
async def prices(_app: None) -> AsyncIterator[FakeListPrices]:
    fake = FakeListPrices({VALID_ISBN: 15000, VALID_ISBN_2: 12000, VALID_ISBN_3: 9000})
    app.dependency_overrides[get_list_prices] = lambda: fake
    yield fake


def _two_items() -> list[dict]:
    return [item_body(VALID_ISBN, 2), item_body(VALID_ISBN_2, 1)]


async def _create(client: AsyncClient, items: list[dict] | None = None, **overrides) -> dict:
    res = await client.post(URL, json=request_body(items or _two_items(), **overrides))
    assert res.status_code == 201, res.text
    return res.json()


async def _pending(client: AsyncClient, items: list[dict] | None = None) -> dict:
    created = await _create(client, items)
    res = await client.post(f"{URL}/{created['id']}/submit")
    assert res.status_code == 200, res.text
    return res.json()


async def _row(session: AsyncSession, request_id: int) -> dict:
    result = await session.execute(
        text("SELECT * FROM purchase_requests WHERE id = :id"), {"id": request_id}
    )
    return dict(result.mappings().one())


async def _item_rows(session: AsyncSession, request_id: int) -> list[dict]:
    result = await session.execute(
        text(
            "SELECT * FROM purchase_request_items WHERE purchase_request_id = :id ORDER BY position"
        ),
        {"id": request_id},
    )
    return [dict(r) for r in result.mappings()]


async def _book_request(session: AsyncSession, request_id: int) -> dict:
    result = await session.execute(
        text("SELECT status, purchase_request_id FROM book_requests WHERE id = :id"),
        {"id": request_id},
    )
    return dict(result.mappings().one())


# --- 만들기와 항목 규칙 ---


async def test_create_draft(admin_client: AsyncClient, prices: FakeListPrices) -> None:
    """[library/purchase-requests] 요청서 만들기 / 정상 만들기"""
    res = await admin_client.post(URL, json=request_body(_two_items(), vendor_name="동네책방"))
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "draft" and body["item_count"] == 2
    assert body["vendor_name"] == "동네책방" and body["total_amount"] is None


@pytest.mark.parametrize("title", [None, "", "가" * 41])
async def test_title_required(admin_client: AsyncClient, session: AsyncSession, title) -> None:
    """[library/purchase-requests] 요청서 만들기 / 제목 누락"""
    body = request_body(_two_items())
    if title is None:
        del body["title"]
    else:
        body["title"] = title
    assert (await admin_client.post(URL, json=body)).status_code == 422
    count = await session.scalar(text("SELECT count(*) FROM purchase_requests"))
    assert count == 0


async def test_external_library_can_create(admin_client_b: AsyncClient, _app: None) -> None:
    """[library/purchase-requests] 요청서 만들기 / 외부 대출 기관"""
    assert (await admin_client_b.post(URL, json=request_body(_two_items()))).status_code == 201


async def test_isbn_normalized(admin_client: AsyncClient, session: AsyncSession) -> None:
    """[library/purchase-requests] 요청서 항목 규칙 / ISBN 정규화"""
    created = await _create(admin_client, [item_body("978-0-306-40615-7")])
    (row,) = await _item_rows(session, created["id"])
    assert row["isbn"] == VALID_ISBN


@pytest.mark.parametrize("isbn", ["9780306406158", "8936434128", None])
async def test_invalid_isbn(admin_client: AsyncClient, isbn) -> None:
    """[library/purchase-requests] 요청서 항목 규칙 / 잘못된 ISBN"""
    item = item_body(VALID_ISBN)
    if isbn is None:
        del item["isbn"]
    else:
        item["isbn"] = isbn
    assert (await admin_client.post(URL, json=request_body([item]))).status_code == 422


async def test_duplicate_isbn_rejected(admin_client: AsyncClient) -> None:
    """[library/purchase-requests] 요청서 항목 규칙 / 같은 ISBN 두 번"""
    items = [item_body(VALID_ISBN), item_body("978-0-306-40615-7")]
    assert (await admin_client.post(URL, json=request_body(items))).status_code == 422


@pytest.mark.parametrize(
    "items",
    [
        [],
        [item_body(make_isbn(n)) for n in range(31)],
        [item_body(VALID_ISBN, 0)],
        [item_body(VALID_ISBN, 11)],
    ],
    ids=["0개", "31개", "권수0", "권수11"],
)
async def test_item_count_and_quantity_limits(admin_client: AsyncClient, items) -> None:
    """[library/purchase-requests] 요청서 항목 규칙 / 항목 수와 권수"""
    assert (await admin_client.post(URL, json=request_body(items))).status_code == 422


async def test_thirty_items_are_allowed(admin_client: AsyncClient) -> None:
    """[library/purchase-requests] 요청서 항목 규칙 / 항목 수와 권수 (상한 30개는 통과)"""
    items = [item_body(make_isbn(n)) for n in range(30)]
    assert (await admin_client.post(URL, json=request_body(items))).status_code == 201


async def test_reason_is_optional(admin_client: AsyncClient) -> None:
    """[library/purchase-requests] 요청서 항목 규칙 / 근거 한 줄 없음"""
    items = [item_body(VALID_ISBN, reason_kind="popular")]
    assert (await admin_client.post(URL, json=request_body(items))).status_code == 201


# --- 고치기·지우기·승인 흐름 ---


async def test_update_draft_replaces_items(
    admin_client: AsyncClient, session: AsyncSession
) -> None:
    """[library/purchase-requests] 초안 고치기와 지우기 / 초안 고치기"""
    created = await _create(admin_client)
    items = [item_body(VALID_ISBN, 1), item_body(VALID_ISBN_2, 2), item_body(VALID_ISBN_3, 3)]
    res = await admin_client.put(f"{URL}/{created['id']}", json=request_body(items, title="수정"))
    assert res.status_code == 200 and res.json()["title"] == "수정"
    rows = await _item_rows(session, created["id"])
    assert [r["isbn"] for r in rows] == [VALID_ISBN, VALID_ISBN_2, VALID_ISBN_3]


async def test_pending_request_cannot_be_edited_or_deleted(admin_client: AsyncClient) -> None:
    """[library/purchase-requests] 초안 고치기와 지우기 / 승인 대기 고치기"""
    pending = await _pending(admin_client)
    url = f"{URL}/{pending['id']}"
    assert (await admin_client.put(url, json=request_body(_two_items()))).status_code == 409
    assert (await admin_client.delete(url)).status_code == 409


async def test_delete_draft(admin_client: AsyncClient, session: AsyncSession) -> None:
    """[library/purchase-requests] 초안 고치기와 지우기 / 초안 지우기"""
    created = await _create(admin_client)
    assert (await admin_client.delete(f"{URL}/{created['id']}")).status_code == 204
    assert await _item_rows(session, created["id"]) == []


async def test_submit_then_reject_keeps_reason(admin_client: AsyncClient) -> None:
    """[library/purchase-requests] 요청서 승인 흐름 / 제출과 반려"""
    pending = await _pending(admin_client)
    assert pending["status"] == "pending_approval"
    res = await admin_client.post(f"{URL}/{pending['id']}/reject", json={"reason": "3번 빼기"})
    assert res.status_code == 200
    assert res.json()["status"] == "draft" and res.json()["rejected_reason"] == "3번 빼기"


async def test_draft_cannot_be_approved(admin_client: AsyncClient, prices: FakeListPrices) -> None:
    """[library/purchase-requests] 요청서 승인 흐름 / 초안 승인"""
    created = await _create(admin_client)
    res = await admin_client.post(f"{URL}/{created['id']}/approve")
    assert res.status_code == 409
    assert prices.calls == []  # 상태가 맞지 않으면 가격을 조회하지 않는다


async def test_list_filters_by_status_newest_first(admin_client: AsyncClient) -> None:
    """[library/purchase-requests] 요청서 조회와 추정 금액 / 목록 (상태 거르기, 최신순)"""
    first = await _create(admin_client)
    second = await _pending(admin_client)
    rows = (await admin_client.get(URL)).json()
    assert [r["id"] for r in rows] == [second["id"], first["id"]]
    pending_only = (await admin_client.get(URL, params={"status": "pending_approval"})).json()
    assert [r["id"] for r in pending_only] == [second["id"]]


# --- 정가 조회와 추정 금액 ---


async def test_estimate_from_looked_up_prices(
    admin_client: AsyncClient, prices: FakeListPrices
) -> None:
    """[library/purchase-requests] 요청서 조회와 추정 금액 / 추정 금액"""
    created = await _create(admin_client)
    body = (await admin_client.get(f"{URL}/{created['id']}")).json()
    assert [(i["unit_price"], i["amount"]) for i in body["items"]] == [
        (15000, 30000),
        (12000, 12000),
    ]
    assert body["estimate"]["estimated_total"] == 42000
    assert body["estimate"]["missing_price_count"] == 0
    assert body["estimate"]["priced_at"] is not None


async def test_estimate_skips_items_without_price(
    admin_client: AsyncClient, prices: FakeListPrices
) -> None:
    """[library/purchase-requests] 요청서 조회와 추정 금액 / 가격 없는 항목"""
    prices.prices[VALID_ISBN_3] = None
    items = [*_two_items(), item_body(VALID_ISBN_3)]
    created = await _create(admin_client, items)
    body = (await admin_client.get(f"{URL}/{created['id']}")).json()
    assert body["items"][2]["unit_price"] is None and body["items"][2]["amount"] is None
    assert body["estimate"]["estimated_total"] == 42000
    assert body["estimate"]["missing_price_count"] == 1


async def test_detail_stores_nothing(
    admin_client: AsyncClient, session: AsyncSession, prices: FakeListPrices
) -> None:
    """[library/purchase-requests] 요청서 조회와 추정 금액 / 저장하지 않음"""
    created = await _create(admin_client)
    assert (await admin_client.get(f"{URL}/{created['id']}")).status_code == 200
    assert prices.calls  # 조회는 했다
    row = await _row(session, created["id"])
    assert row["total_amount"] is None and row["priced_at"] is None and row["price_source"] is None
    for item in await _item_rows(session, created["id"]):
        assert item["unit_price"] is None and item["amount"] is None


async def test_list_does_not_look_up_prices(
    admin_client: AsyncClient, prices: FakeListPrices
) -> None:
    """[library/purchase-requests] 요청서 조회와 추정 금액 / 목록은 조회하지 않음"""
    await _create(admin_client)
    assert (await admin_client.get(URL)).status_code == 200
    assert prices.calls == []


async def test_detail_when_lookup_unavailable(
    admin_client: AsyncClient, prices: FakeListPrices
) -> None:
    """[library/purchase-requests] 승인 때 조회 실패 / 조회 장애 상세"""
    prices.unavailable = True
    created = await _create(admin_client)
    res = await admin_client.get(f"{URL}/{created['id']}")
    assert res.status_code == 200
    body = res.json()
    assert body["estimate"]["unavailable"] is True and body["estimate"]["estimated_total"] is None
    assert all(i["unit_price"] is None and i["amount"] is None for i in body["items"])


async def test_lookup_price_wins_over_official_book_price(
    admin_client: AsyncClient, session: AsyncSession, prices: FakeListPrices
) -> None:
    """[library/purchase-requests] 정가 조회 / 공식 서지 정가를 쓰지 않음"""
    await add_book(session, VALID_ISBN, list_price=12000)
    created = await _create(admin_client, [item_body(VALID_ISBN)])
    body = (await admin_client.get(f"{URL}/{created['id']}")).json()
    assert body["items"][0]["unit_price"] == 15000
    stored = await session.scalar(
        text("SELECT list_price FROM books WHERE isbn = :i"), {"i": VALID_ISBN}
    )
    assert stored == 12000


# --- 승인: 금액 기록과 실패 ---


async def test_approve_records_amounts(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant, prices: FakeListPrices
) -> None:
    """[library/purchase-requests] 승인 때 금액 기록 / 기록한 금액"""
    pending = await _pending(admin_client)
    res = await admin_client.post(f"{URL}/{pending['id']}/approve")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "confirmed" and body["total_amount"] == 42000
    assert body["price_source"] == "yes24_list_price" and body["priced_at"] is not None
    assert body["approved_by"] == library_a.admin["id"] and body["confirmed_at"] is not None
    rows = await _item_rows(session, pending["id"])
    assert [(r["unit_price"], r["amount"]) for r in rows] == [(15000, 30000), (12000, 12000)]


async def test_recorded_price_is_the_one_looked_up_at_approval(
    admin_client: AsyncClient, session: AsyncSession, prices: FakeListPrices
) -> None:
    """[library/purchase-requests] 승인 때 금액 기록 / 상세 뒤 가격이 바뀜"""
    pending = await _pending(admin_client)
    detail = (await admin_client.get(f"{URL}/{pending['id']}")).json()
    assert detail["items"][0]["unit_price"] == 15000
    prices.prices[VALID_ISBN] = 16000
    assert (await admin_client.post(f"{URL}/{pending['id']}/approve")).status_code == 200
    rows = await _item_rows(session, pending["id"])
    assert rows[0]["unit_price"] == 16000 and rows[0]["amount"] == 32000
    assert (await _row(session, pending["id"]))["total_amount"] == 44000


async def test_approve_with_missing_price_changes_nothing(
    admin_client: AsyncClient, session: AsyncSession, prices: FakeListPrices
) -> None:
    """[library/purchase-requests] 승인 때 조회 실패 / 가격 없는 항목 승인"""
    prices.prices[VALID_ISBN_2] = None
    pending = await _pending(admin_client)
    res = await admin_client.post(f"{URL}/{pending['id']}/approve")
    assert res.status_code == 409 and VALID_ISBN_2 in res.json()["detail"]
    row = await _row(session, pending["id"])
    assert row["status"] == "pending_approval" and row["total_amount"] is None
    assert row["approved_at"] is None


async def test_approve_when_lookup_unavailable_changes_nothing(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant, prices: FakeListPrices
) -> None:
    """[library/purchase-requests] 승인 때 조회 실패 / 조회 장애 승인"""
    member = await add_member(session, library_a.id, "M0001")
    requested = await add_book_request(
        session, library_a.id, member_id=member["id"], isbn=VALID_ISBN
    )
    pending = await _pending(admin_client)
    prices.unavailable = True
    res = await admin_client.post(f"{URL}/{pending['id']}/approve")
    assert res.status_code == 503
    row = await _row(session, pending["id"])
    assert row["status"] == "pending_approval" and row["total_amount"] is None
    assert row["approved_at"] is None and row["approved_by"] is None
    assert (await _book_request(session, requested["id"]))["status"] == "requested"
    for item in await _item_rows(session, pending["id"]):
        assert item["unit_price"] is None and item["amount"] is None


async def test_overlapping_approvals_confirm_once(
    admin_client: AsyncClient, session: AsyncSession, prices: FakeListPrices
) -> None:
    """[library/purchase-requests] 요청서 승인 흐름 / 겹친 승인

    첫 승인이 가격을 조회하는 동안 같은 요청서의 두 번째 승인이 끝까지 간다.
    """
    pending = await _pending(admin_client)
    nested: list[int] = []

    async def second_approval() -> None:
        res = await admin_client.post(f"{URL}/{pending['id']}/approve")
        nested.append(res.status_code)

    prices.during = second_approval
    first = await admin_client.post(f"{URL}/{pending['id']}/approve")
    assert nested == [200] and first.status_code == 409
    row = await _row(session, pending["id"])
    assert row["status"] == "confirmed" and row["total_amount"] == 42000


async def test_request_changed_while_pricing_is_not_confirmed(
    admin_client: AsyncClient, session: AsyncSession, prices: FakeListPrices
) -> None:
    """[library/purchase-requests] 승인 때 금액 기록 / 가격을 조회하는 동안 항목이 바뀜"""
    pending = await _pending(admin_client)

    async def reject_edit_resubmit() -> None:
        url = f"{URL}/{pending['id']}"
        await admin_client.post(f"{url}/reject", json={"reason": "바꿈"})
        await admin_client.put(url, json=request_body([item_body(VALID_ISBN_3, 1)]))
        await admin_client.post(f"{url}/submit")

    prices.during = reject_edit_resubmit
    res = await admin_client.post(f"{URL}/{pending['id']}/approve")
    assert res.status_code == 409
    row = await _row(session, pending["id"])
    assert row["status"] == "pending_approval" and row["total_amount"] is None
    (item,) = await _item_rows(session, pending["id"])
    assert item["isbn"] == VALID_ISBN_3 and item["unit_price"] is None


# --- 확정본 ---


async def test_confirmed_request_is_immutable(
    admin_client: AsyncClient, session: AsyncSession, prices: FakeListPrices
) -> None:
    """[library/purchase-requests] 확정본은 바꾸지 않음 / 확정본 고치기"""
    pending = await _pending(admin_client)
    assert (await admin_client.post(f"{URL}/{pending['id']}/approve")).status_code == 200
    url = f"{URL}/{pending['id']}"
    assert (await admin_client.put(url, json=request_body(_two_items()))).status_code == 409
    assert (await admin_client.delete(url)).status_code == 409
    assert (await admin_client.post(f"{url}/submit")).status_code == 409
    assert (await admin_client.post(f"{url}/reject", json={"reason": "x"})).status_code == 409
    assert (await admin_client.post(f"{url}/approve")).status_code == 409
    row = await _row(session, pending["id"])
    assert row["status"] == "confirmed" and row["total_amount"] == 42000


async def test_confirmed_detail_is_recorded_values_without_lookup(
    admin_client: AsyncClient, prices: FakeListPrices
) -> None:
    """[library/purchase-requests] 요청서 조회와 추정 금액 / 확정본 상세"""
    pending = await _pending(admin_client)
    await admin_client.post(f"{URL}/{pending['id']}/approve")
    prices.prices[VALID_ISBN] = 99000  # 확정 뒤 가격이 바뀌어도
    calls = len(prices.calls)
    body = (await admin_client.get(f"{URL}/{pending['id']}")).json()
    assert len(prices.calls) == calls
    assert body["estimate"] is None and body["total_amount"] == 42000
    assert [(i["unit_price"], i["amount"]) for i in body["items"]] == [
        (15000, 30000),
        (12000, 12000),
    ]


# --- 확정 때 희망도서 닫기 ---


async def test_confirm_closes_same_isbn_requests(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant, prices: FakeListPrices
) -> None:
    """[library/purchase-requests] 확정 때 희망도서 닫기 / 같은 ISBN 신청 둘"""
    m1 = await add_member(session, library_a.id, "M0001")
    m2 = await add_member(session, library_a.id, "M0002")
    a = await add_book_request(session, library_a.id, member_id=m1["id"], isbn=VALID_ISBN)
    b = await add_book_request(session, library_a.id, member_id=m2["id"], isbn=VALID_ISBN)
    items = [item_body(VALID_ISBN, 1, reason_kind="book_request")]
    pending = await _pending(admin_client, items)
    assert (await admin_client.post(f"{URL}/{pending['id']}/approve")).status_code == 200
    for request in (a, b):
        assert await _book_request(session, request["id"]) == {
            "status": "closed",
            "purchase_request_id": pending["id"],
        }


async def test_admin_list_shows_purchase_request_of_closed_request(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant, prices: FakeListPrices
) -> None:
    """[circulation/book-requests] 희망도서 목록과 닫기 / 요청서로 닫힌 신청"""
    member = await add_member(session, library_a.id, "M0001")
    await add_book_request(session, library_a.id, member_id=member["id"], isbn=VALID_ISBN)
    pending = await _pending(admin_client, [item_body(VALID_ISBN, 1)])
    before = (await admin_client.get("/book-requests")).json()["items"]
    assert before[0]["status"] == "requested" and before[0]["purchase_request_id"] is None
    await admin_client.post(f"{URL}/{pending['id']}/approve")
    (row,) = (await admin_client.get("/book-requests")).json()["items"]
    assert row["status"] == "closed" and row["purchase_request_id"] == pending["id"]


async def test_confirm_closes_requests_for_manual_items(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant, prices: FakeListPrices
) -> None:
    """[library/purchase-requests] 확정 때 희망도서 닫기 / 직접 넣은 항목"""
    member = await add_member(session, library_a.id, "M0001")
    request = await add_book_request(session, library_a.id, member_id=member["id"], isbn=VALID_ISBN)
    pending = await _pending(admin_client, [item_body(VALID_ISBN, 1, reason_kind="manual")])
    await admin_client.post(f"{URL}/{pending['id']}/approve")
    assert (await _book_request(session, request["id"]))["status"] == "closed"


async def test_confirm_leaves_other_requests(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant, prices: FakeListPrices
) -> None:
    """[library/purchase-requests] 확정 때 희망도서 닫기 / 닫지 않는 신청"""
    member = await add_member(session, library_a.id, "M0001")
    no_isbn = await add_book_request(
        session, library_a.id, member_id=member["id"], title="ISBN 없음"
    )
    already = await add_book_request(
        session,
        library_a.id,
        member_id=member["id"],
        title="닫힌 책",
        isbn=VALID_ISBN,
        status="closed",
    )
    other_isbn = await add_book_request(
        session, library_a.id, member_id=member["id"], title="다른 책", isbn=VALID_ISBN_3
    )
    pending = await _pending(admin_client, [item_body(VALID_ISBN, 1)])
    await admin_client.post(f"{URL}/{pending['id']}/approve")
    assert await _book_request(session, no_isbn["id"]) == {
        "status": "requested",
        "purchase_request_id": None,
    }
    assert await _book_request(session, already["id"]) == {
        "status": "closed",
        "purchase_request_id": None,
    }
    assert (await _book_request(session, other_isbn["id"]))["status"] == "requested"


async def test_confirm_does_not_close_other_library_requests(
    admin_client: AsyncClient, session: AsyncSession, library_b: Tenant, prices: FakeListPrices
) -> None:
    """[library/purchase-requests] 확정 때 희망도서 닫기 / 다른 기관의 같은 ISBN"""
    member_b = await add_member(session, library_b.id, "M0001")
    other = await add_book_request(session, library_b.id, member_id=member_b["id"], isbn=VALID_ISBN)
    pending = await _pending(admin_client, [item_body(VALID_ISBN, 1)])
    await admin_client.post(f"{URL}/{pending['id']}/approve")
    assert await _book_request(session, other["id"]) == {
        "status": "requested",
        "purchase_request_id": None,
    }


# --- 권한과 기관 분리 ---


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", ""),
        ("get", ""),
        ("get", "/1"),
        ("put", "/1"),
        ("delete", "/1"),
        ("post", "/1/submit"),
        ("post", "/1/approve"),
        ("post", "/1/reject"),
    ],
)
async def test_kiosk_is_forbidden(
    kiosk_client: AsyncClient, prices: FakeListPrices, method: str, path: str
) -> None:
    """[library/purchase-requests] 요청서 만들기 / 키오스크"""
    body = {"reason": "x"} if path.endswith("reject") else request_body(_two_items())
    res = await kiosk_client.request(method, f"{URL}{path}", json=body)
    assert res.status_code == 403


@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("get", ""),
        ("put", ""),
        ("delete", ""),
        ("post", "/submit"),
        ("post", "/approve"),
        ("post", "/reject"),
    ],
)
async def test_other_library_request_is_not_found(
    admin_client: AsyncClient,
    admin_client_b: AsyncClient,
    session: AsyncSession,
    prices: FakeListPrices,
    method: str,
    suffix: str,
) -> None:
    """[library/purchase-requests] 구매 요청서의 기관 분리 / 다른 기관 요청서"""
    theirs = await _pending(admin_client_b)
    body = {"reason": "x"} if suffix == "/reject" else request_body(_two_items())
    res = await admin_client.request(method, f"{URL}/{theirs['id']}{suffix}", json=body)
    assert res.status_code == 404
    assert (await _row(session, theirs["id"]))["status"] == "pending_approval"
    assert prices.calls == []


async def test_list_shows_only_own_library(
    admin_client: AsyncClient, admin_client_b: AsyncClient
) -> None:
    """[library/purchase-requests] 구매 요청서의 기관 분리 / 다른 기관 목록과 후보 (목록)"""
    mine = await _create(admin_client)
    await _create(admin_client_b)
    assert [r["id"] for r in (await admin_client.get(URL)).json()] == [mine["id"]]
