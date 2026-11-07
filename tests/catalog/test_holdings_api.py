"""[catalog/holdings] 소장 사본 REST API."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from tests.conftest import Tenant
from tests.helpers import (
    VALID_ISBN_2,
    add_holding,
    add_library_book,
    add_loan,
    add_member,
    assert_rejected,
    fetch,
)

CALL_NUMBER = "813.7-한232ㅊ"


def _purchased(library_book_id: int, accession_number: str = "EM0001", **overrides) -> dict:
    return {
        "library_book_id": library_book_id,
        "accession_number": accession_number,
        "acquisition_type": "purchased",
        "purchase_price": 15000,
        **overrides,
    }


def _donated(library_book_id: int, accession_number: str = "EM0001", **overrides) -> dict:
    return {
        "library_book_id": library_book_id,
        "accession_number": accession_number,
        "acquisition_type": "donated",
        **overrides,
    }


# --- 사본 등록 ---


async def test_create_holding(
    library_a: Tenant, admin_client: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/holdings] 사본 등록 / 정상 등록"""
    book = await add_library_book(session, library_a.id)
    res = await admin_client.post("/holdings", json=_purchased(book["id"], call_number=CALL_NUMBER))
    assert res.status_code == 201
    body = res.json()
    assert body["accession_number"] == "EM0001"
    assert body["call_number"] == CALL_NUMBER
    assert (body["status"], body["source"]) == ("available", "manual")
    assert (body["acquisition_type"], body["purchase_price"]) == ("purchased", 15000)
    assert (body["title"], body["isbn"]) == ("테스트 도서", book["isbn"])


async def test_two_copies_same_book(
    library_a: Tenant, admin_client: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/holdings] 사본 등록 / 같은 책 두 권"""
    book = await add_library_book(session, library_a.id)
    for acc in ("EM0001", "EM0002"):
        res = await admin_client.post(
            "/holdings", json=_purchased(book["id"], acc, call_number=CALL_NUMBER)
        )
        assert res.status_code == 201
    listed = (await admin_client.get("/holdings", params={"library_book_id": book["id"]})).json()
    assert listed["total"] == 2


async def test_unknown_book(admin_client: AsyncClient) -> None:
    """[catalog/holdings] 사본 등록 / 도서 목록에 없는 도서"""
    assert (await admin_client.post("/holdings", json=_purchased(999999))).status_code == 404


# --- 등록번호 유일성 ---


async def test_duplicate_accession_number(
    library_a: Tenant, admin_client: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/holdings] 등록번호 유일성 / 같은 기관에서 중복"""
    book = await add_library_book(session, library_a.id)
    await admin_client.post("/holdings", json=_purchased(book["id"]))
    assert (await admin_client.post("/holdings", json=_purchased(book["id"]))).status_code == 409


async def test_same_number_other_library(
    library_a: Tenant,
    library_b: Tenant,
    admin_client: AsyncClient,
    admin_client_b: AsyncClient,
    session: AsyncSession,
) -> None:
    """[catalog/holdings] 등록번호 유일성 / 다른 기관의 같은 번호"""
    ours = await add_library_book(session, library_a.id)
    theirs = await add_library_book(session, library_b.id)
    assert (await admin_client.post("/holdings", json=_purchased(ours["id"]))).status_code == 201
    assert (
        await admin_client_b.post("/holdings", json=_purchased(theirs["id"]))
    ).status_code == 201


async def test_create_with_other_library_book(
    library_b: Tenant, admin_client: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/holdings] 사본 등록 / 다른 기관의 도서"""
    theirs = await add_library_book(session, library_b.id)
    res = await admin_client.post("/holdings", json=_purchased(theirs["id"]))
    assert res.status_code == 404
    assert (await admin_client.get("/holdings")).json()["total"] == 0


# --- 입수 구분 ---


async def test_donated_holding(
    library_a: Tenant, admin_client: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/holdings] 입수 구분 / 기증 사본 등록"""
    book = await add_library_book(session, library_a.id, None, list_price=None)
    res = await admin_client.post("/holdings", json=_donated(book["id"], donor="주민 기증"))
    assert res.status_code == 201
    body = res.json()
    assert (body["acquisition_type"], body["donor"], body["purchase_price"]) == (
        "donated",
        "주민 기증",
        None,
    )


async def test_purchased_without_price(
    library_a: Tenant, admin_client: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/holdings] 입수 구분 / 구입가 없는 매입 사본"""
    book = await add_library_book(session, library_a.id)
    payload = _purchased(book["id"])
    del payload["purchase_price"]
    assert (await admin_client.post("/holdings", json=payload)).status_code == 422
    assert (await admin_client.get("/holdings")).json()["total"] == 0


async def test_purchased_needs_isbn(
    library_a: Tenant, admin_client: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/holdings] 입수 구분 / ISBN 없는 도서로 매입 사본"""
    book = await add_library_book(session, library_a.id, None)
    res = await admin_client.post("/holdings", json=_purchased(book["id"], purchase_price=12000))
    assert res.status_code == 422
    assert "ISBN" in res.json()["detail"]


async def test_donated_with_price(
    library_a: Tenant, admin_client: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/holdings] 입수 구분 / 기증 사본에 구입가 (매입 사본의 기증처도 거부)"""
    book = await add_library_book(session, library_a.id)
    res = await admin_client.post("/holdings", json=_donated(book["id"], purchase_price=5000))
    assert res.status_code == 422
    res = await admin_client.post("/holdings", json=_purchased(book["id"], donor="주민"))
    assert res.status_code == 422


async def test_acquisition_rules_in_db(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/holdings] 입수 구분 / 입수 구분 규칙 직접 저장"""
    book = await add_library_book(session, library_a.id)
    base = {"library_id": library_a.id, "library_book_id": book["id"]}
    await assert_rejected(
        session,
        "holdings",
        **base,
        accession_number="X1",
        acquisition_type="purchased",
        match="acquisition_fields",
    )
    await assert_rejected(
        session,
        "holdings",
        **base,
        accession_number="X2",
        acquisition_type="donated",
        purchase_price=1000,
        match="acquisition_fields",
    )


async def test_update_acquisition_follows_rules(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/holdings] 입수 구분 (수정할 때도 같은 규칙)"""
    no_isbn = await add_library_book(session, library_a.id, None)
    donated = await add_holding(
        session, library_a.id, no_isbn["id"], "D-1", acquisition_type="donated", purchase_price=None
    )
    # ISBN 없는 도서의 기증 사본을 매입으로 바꿀 수 없다
    res = await admin_client.patch(
        f"/holdings/{donated['id']}", json={"acquisition_type": "purchased", "purchase_price": 1}
    )
    assert res.status_code == 422
    # 구입가 없이 매입으로 바꿀 수 없다
    book = await add_library_book(session, library_a.id, VALID_ISBN_2)
    other = await add_holding(
        session, library_a.id, book["id"], "D-2", acquisition_type="donated", purchase_price=None
    )
    res = await admin_client.patch(
        f"/holdings/{other['id']}", json={"acquisition_type": "purchased"}
    )
    assert res.status_code == 422
    res = await admin_client.patch(
        f"/holdings/{other['id']}", json={"acquisition_type": "purchased", "purchase_price": 9000}
    )
    assert res.status_code == 200
    assert res.json()["purchase_price"] == 9000


# --- 사본 상태 ---


async def test_mark_lost(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/holdings] 사본 상태 / 분실 처리"""
    book = await add_library_book(session, library_a.id)
    holding = await add_holding(session, library_a.id, book["id"], "A-1")
    res = await admin_client.patch(f"/holdings/{holding['id']}", json={"status": "lost"})
    assert res.status_code == 200
    assert res.json()["status"] == "lost"


async def test_cannot_set_on_loan(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/holdings] 사본 상태 / 직접 대출 중으로 바꾸기 (등록 시 포함)"""
    book = await add_library_book(session, library_a.id)
    holding = await add_holding(session, library_a.id, book["id"], "A-1")
    res = await admin_client.patch(f"/holdings/{holding['id']}", json={"status": "on_loan"})
    assert res.status_code == 409
    res = await admin_client.post("/holdings", json=_purchased(book["id"], "A-2", status="on_loan"))
    assert res.status_code == 409


async def test_cannot_change_on_loan(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/holdings] 사본 상태 / 대출 중인 사본의 상태 변경"""
    book = await add_library_book(session, library_a.id)
    holding = await add_holding(session, library_a.id, book["id"], "A-1")
    await add_loan(session, holding, await add_member(session, library_a.id, "M1"))
    res = await admin_client.patch(f"/holdings/{holding['id']}", json={"status": "lost"})
    assert res.status_code == 409
    assert "반납" in res.json()["detail"]


async def test_unknown_status_rejected_by_db(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/holdings] 사본 상태 / 허용되지 않은 상태"""
    book = await add_library_book(session, library_a.id)
    await assert_rejected(
        session,
        "holdings",
        library_id=library_a.id,
        library_book_id=book["id"],
        accession_number="X1",
        acquisition_type="donated",
        status="missing",
        match="holding_status",
    )


# --- 사본 조회 ---


async def test_filter_by_book(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/holdings] 사본 조회 / 도서로 거르기"""
    book = await add_library_book(session, library_a.id)
    other = await add_library_book(session, library_a.id, VALID_ISBN_2)
    mine = await add_holding(session, library_a.id, book["id"], "A-1")
    await add_holding(session, library_a.id, other["id"], "A-2")
    theirs = await add_library_book(session, library_b.id)
    await add_holding(session, library_b.id, theirs["id"], "B-1")
    res = await kiosk_client.get("/holdings", params={"library_book_id": book["id"]})
    assert res.status_code == 200
    assert [h["id"] for h in res.json()["items"]] == [mine["id"]]


async def test_filter_by_status(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/holdings] 사본 조회 / 상태로 거르기"""
    book = await add_library_book(session, library_a.id)
    ok = await add_holding(session, library_a.id, book["id"], "A-1")
    await add_holding(session, library_a.id, book["id"], "A-2", status="lost")
    res = await admin_client.get("/holdings", params={"status": "available"})
    assert [h["id"] for h in res.json()["items"]] == [ok["id"]]


async def test_other_library_holding_is_404(
    admin_client: AsyncClient, session: AsyncSession, library_b: Tenant
) -> None:
    """[library/libraries] 기관 데이터 분리 / 다른 기관의 사본 조회 (수정·삭제도 404)"""
    book = await add_library_book(session, library_b.id)
    theirs = await add_holding(session, library_b.id, book["id"], "B-1")
    url = f"/holdings/{theirs['id']}"
    assert (await admin_client.get(url)).status_code == 404
    assert (await admin_client.patch(url, json={"shelf_location": "x"})).status_code == 404
    assert (await admin_client.delete(url)).status_code == 404
    assert (await fetch(session, "holdings", theirs["id"]))["shelf_location"] is None


async def test_no_token(client: AsyncClient) -> None:
    """[library/staff-auth] 토큰 검증과 로그아웃 / 토큰 없이 호출"""
    assert (await client.get("/holdings")).status_code == 401


async def test_kiosk_cannot_write(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/staff-auth] 역할별 접근 제한 (키오스크는 사본 조회만)"""
    book = await add_library_book(session, library_a.id)
    holding = await add_holding(session, library_a.id, book["id"], "A-1")
    assert (
        await kiosk_client.post("/holdings", json=_purchased(book["id"], "A-9"))
    ).status_code == 403
    assert (
        await kiosk_client.patch(f"/holdings/{holding['id']}", json={"status": "lost"})
    ).status_code == 403
    assert (await kiosk_client.delete(f"/holdings/{holding['id']}")).status_code == 403
    assert (await kiosk_client.get(f"/holdings/{holding['id']}")).status_code == 200


# --- 사본 수정과 삭제 ---


async def test_update_shelf_only(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/holdings] 사본 수정과 삭제 / 서가 위치 수정"""
    book = await add_library_book(session, library_a.id)
    holding = await add_holding(session, library_a.id, book["id"], "A-1", call_number=CALL_NUMBER)
    res = await admin_client.patch(
        f"/holdings/{holding['id']}", json={"shelf_location": "어린이 자료실"}
    )
    body = res.json()
    assert body["shelf_location"] == "어린이 자료실"
    assert (body["accession_number"], body["call_number"], body["status"]) == (
        "A-1",
        CALL_NUMBER,
        "available",
    )


async def test_delete_without_loans(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/holdings] 사본 수정과 삭제 / 대출 기록 없는 사본 삭제"""
    book = await add_library_book(session, library_a.id)
    holding = await add_holding(session, library_a.id, book["id"], "A-1")
    assert (await admin_client.delete(f"/holdings/{holding['id']}")).status_code == 204
    assert (await admin_client.get(f"/holdings/{holding['id']}")).status_code == 404


async def test_delete_with_loans(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/holdings] 사본 수정과 삭제 / 대출 기록 있는 사본 삭제"""
    book = await add_library_book(session, library_a.id)
    holding = await add_holding(session, library_a.id, book["id"], "A-1")
    member = await add_member(session, library_a.id, "M1")
    await add_loan(session, holding, member, returned_on=clock.today())  # 반납된 기록
    assert (await admin_client.delete(f"/holdings/{holding['id']}")).status_code == 409
    assert (await admin_client.get(f"/holdings/{holding['id']}")).status_code == 200


# --- 입수 구분 unknown, 제적, 빠진 정보 ---


async def _imported(
    session: AsyncSession, library_id: int, library_book_id: int, acc: str, **overrides
):
    values = {"source": "imported", "acquisition_type": "purchased", "purchase_price": None}
    return await add_holding(session, library_id, library_book_id, acc, **{**values, **overrides})


async def test_create_unknown_rejected(
    library_a: Tenant, admin_client: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/holdings] 입수 구분 / 직접 등록의 unknown"""
    book = await add_library_book(session, library_a.id)
    res = await admin_client.post(
        "/holdings", json=_donated(book["id"]) | {"acquisition_type": "unknown"}
    )
    assert res.status_code == 422


async def test_unknown_to_donated(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/holdings] 입수 구분 / unknown을 기증으로 수정"""
    book = await add_library_book(session, library_a.id)
    holding = await _imported(session, library_a.id, book["id"], "A-1", acquisition_type="unknown")
    res = await admin_client.patch(
        f"/holdings/{holding['id']}", json={"acquisition_type": "donated"}
    )
    assert res.status_code == 200
    assert res.json()["acquisition_type"] == "donated"


async def test_fill_price_on_imported_purchase(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/holdings] 입수 구분 / 가져온 매입 사본의 구입가 채우기"""
    book = await add_library_book(session, library_a.id, None)
    holding = await _imported(session, library_a.id, book["id"], "A-1")
    res = await admin_client.patch(f"/holdings/{holding['id']}", json={"purchase_price": 9000})
    assert res.status_code == 200
    assert res.json()["purchase_price"] == 9000
    assert res.json()["missing_fields"] == ["isbn"]


async def test_imported_unknown_to_purchased_needs_isbn(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/holdings] 입수 구분 / 가져온 unknown 사본을 매입으로 수정"""
    book = await add_library_book(session, library_a.id, None)
    holding = await _imported(session, library_a.id, book["id"], "A-1", acquisition_type="unknown")
    res = await admin_client.patch(
        f"/holdings/{holding['id']}", json={"acquisition_type": "purchased", "purchase_price": 9000}
    )
    assert res.status_code == 422


async def test_imported_purchase_without_price_in_db(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/holdings] 입수 구분 / 가져온 매입 사본의 구입가 없음 직접 저장"""
    book = await add_library_book(session, library_a.id)
    row = await _imported(session, library_a.id, book["id"], "A-1")
    assert row["purchase_price"] is None
    # 직접 등록 사본은 여전히 거부한다
    await assert_rejected(
        session,
        "holdings",
        library_id=library_a.id,
        library_book_id=book["id"],
        accession_number="A-2",
        acquisition_type="purchased",
        match="acquisition_fields",
    )
    await assert_rejected(
        session,
        "holdings",
        library_id=library_a.id,
        library_book_id=book["id"],
        accession_number="A-3",
        acquisition_type="unknown",
        donor="주민",
        match="acquisition_fields",
    )


async def test_withdraw(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/holdings] 사본 상태 / 제적 처리"""
    book = await add_library_book(session, library_a.id)
    holding = await add_holding(session, library_a.id, book["id"], "A-1")
    res = await admin_client.patch(f"/holdings/{holding['id']}", json={"status": "withdrawn"})
    assert res.status_code == 200
    assert res.json()["status"] == "withdrawn"


async def test_list_excludes_withdrawn(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/holdings] 사본 조회 / 제적 사본 제외"""
    book = await add_library_book(session, library_a.id)
    kept = await add_holding(session, library_a.id, book["id"], "A-1")
    await add_holding(session, library_a.id, book["id"], "A-2", status="withdrawn")
    body = (await admin_client.get("/holdings")).json()
    assert [h["id"] for h in body["items"]] == [kept["id"]]
    assert body["total"] == 1


async def test_list_only_withdrawn(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/holdings] 사본 조회 / 제적 사본만 보기"""
    book = await add_library_book(session, library_a.id)
    await add_holding(session, library_a.id, book["id"], "A-1")
    gone = await add_holding(session, library_a.id, book["id"], "A-2", status="withdrawn")
    res = await admin_client.get("/holdings", params={"status": "withdrawn"})
    assert [h["id"] for h in res.json()["items"]] == [gone["id"]]


async def test_missing_isbn_marked(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/holdings] 빠진 정보 표기 / ISBN 없는 매입 사본 표기"""
    book = await add_library_book(session, library_a.id, None)
    holding = await _imported(session, library_a.id, book["id"], "A-1", purchase_price=9000)
    body = (await admin_client.get(f"/holdings/{holding['id']}")).json()
    assert body["missing_fields"] == ["isbn"]


async def test_mark_clears_after_isbn_filled(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/holdings] 빠진 정보 표기 / ISBN을 채우면 표기가 사라짐"""
    book = await add_library_book(session, library_a.id, None)
    holding = await _imported(session, library_a.id, book["id"], "A-1", purchase_price=9000)
    res = await admin_client.patch(f"/library-books/{book['id']}", json={"isbn": VALID_ISBN_2})
    assert res.status_code == 200
    body = (await admin_client.get(f"/holdings/{holding['id']}")).json()
    assert body["missing_fields"] == []


async def test_incomplete_filter(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/holdings] 빠진 정보 표기 / 빠진 정보가 있는 사본만 거르기"""
    no_isbn = await add_library_book(session, library_a.id, None)
    book = await add_library_book(session, library_a.id, VALID_ISBN_2)
    a = await _imported(session, library_a.id, no_isbn["id"], "A-1", purchase_price=9000)
    b = await _imported(session, library_a.id, book["id"], "A-2")
    await add_holding(session, library_a.id, book["id"], "A-3")  # 완전한 매입 사본
    theirs = await add_library_book(session, library_b.id, VALID_ISBN_2)
    await _imported(session, library_b.id, theirs["id"], "B-1")  # 다른 기관
    res = await admin_client.get("/holdings", params={"incomplete": "true"})
    assert {h["id"] for h in res.json()["items"]} == {a["id"], b["id"]}


async def test_donated_not_marked(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/holdings] 빠진 정보 표기 / 기증 사본은 표기하지 않음"""
    book = await add_library_book(session, library_a.id, None)
    holding = await add_holding(
        session, library_a.id, book["id"], "A-1", acquisition_type="donated", purchase_price=None
    )
    body = (await admin_client.get(f"/holdings/{holding['id']}")).json()
    assert body["missing_fields"] == []
