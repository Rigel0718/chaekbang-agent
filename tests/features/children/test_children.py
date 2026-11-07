"""[features/children] 어린이 구분: 조회, 지정, 목록, 파일 근거, 외부 분류 근거, 갱신."""

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.features.children import service
from app.features.children.models import Audience, AudienceSource
from app.library.models.catalog import LibraryBook
from tests.catalog.import_helpers import import_file
from tests.conftest import Tenant
from tests.helpers import (
    VALID_ISBN,
    VALID_ISBN_2,
    add_audience,
    add_book,
    add_holding,
    add_library_book,
    assert_rejected,
)
from tests.yes24_helpers import FakeYes24, enrich, item, ok

HEADER = ["등록번호", "서명", "저자"]
GENERAL = ("general", "default")
BOOK = {"isbn": VALID_ISBN, "title": "모모", "author": "미하엘 엔데"}


async def _audience(client: AsyncClient, book_id: int) -> tuple[str, str]:
    res = await client.get(f"/children/books/{book_id}")
    assert res.status_code == 200, res.text
    return res.json()["audience"], res.json()["audience_source"]


async def _stored_rows(session: AsyncSession) -> int:
    return await session.scalar(text("SELECT count(*) FROM library_book_audiences"))


async def _imported_id(session: AsyncSession, accession: str = "EM1") -> int:
    return await session.scalar(
        text("SELECT library_book_id FROM holdings WHERE accession_number = :a"), {"a": accession}
    )


async def _held(session: AsyncSession, library_id: int, isbn: str | None = VALID_ISBN, **overrides):
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


# --- 어린이 구분 ---


async def test_default(admin_client: AsyncClient, session: AsyncSession, library_a: Tenant) -> None:
    """[features/children] 어린이 구분 / 기본값"""
    book = await add_library_book(session, library_a.id)
    assert await _audience(admin_client, book["id"]) == GENERAL
    assert await _stored_rows(session) == 0


async def test_per_library(admin_client: AsyncClient, admin_client_b: AsyncClient) -> None:
    """[features/children] 어린이 구분 / 기관별 구분"""
    ours = (await admin_client.post("/library-books", json=BOOK)).json()
    theirs = (await admin_client_b.post("/library-books", json=BOOK)).json()
    await admin_client.put(f"/children/books/{ours['id']}", json={"audience": "children"})
    assert await _audience(admin_client_b, theirs["id"]) == GENERAL


async def test_rejects_unknown_audience(session: AsyncSession, library_a: Tenant) -> None:
    """[features/children] 어린이 구분 / 허용되지 않은 구분"""
    book = await add_library_book(session, library_a.id)
    await assert_rejected(
        session,
        "library_book_audiences",
        library_id=library_a.id,
        library_book_id=book["id"],
        audience="teen",
        audience_source="manual",
        match="audience",
    )


async def test_rejects_stored_default(session: AsyncSession, library_a: Tenant) -> None:
    """[features/children] 어린이 구분 (default는 저장하지 않음)"""
    book = await add_library_book(session, library_a.id)
    await assert_rejected(
        session,
        "library_book_audiences",
        library_id=library_a.id,
        library_book_id=book["id"],
        audience="general",
        audience_source="default",
        match="source_not_default",
    )


async def test_deleted_with_library_book(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[features/children] 어린이 구분 / 기관 도서와 함께 삭제"""
    book = await add_library_book(session, library_a.id)
    await add_audience(session, library_a.id, book["id"])
    assert (await admin_client.delete(f"/library-books/{book['id']}")).status_code == 204
    assert await _stored_rows(session) == 0


# --- 어린이 구분 조회 ---


async def test_kiosk_can_read(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[features/children] 어린이 구분 조회 / 키오스크 조회"""
    book = await add_library_book(session, library_a.id)
    assert await _audience(kiosk_client, book["id"]) == GENERAL


async def test_kiosk_can_list(kiosk_client: AsyncClient) -> None:
    """[library/staff-auth] 역할별 접근 제한 (키오스크의 어린이 도서 조회)"""
    assert (await kiosk_client.get("/children/books")).status_code == 200


async def test_read_other_library(
    admin_client: AsyncClient, session: AsyncSession, library_b: Tenant
) -> None:
    """[features/children] 어린이 구분 조회 / 다른 기관 도서"""
    theirs = await add_library_book(session, library_b.id)
    assert (await admin_client.get(f"/children/books/{theirs['id']}")).status_code == 404


# --- 관리자 지정 ---


async def test_manual(admin_client: AsyncClient, session: AsyncSession, library_a: Tenant) -> None:
    """[features/children] 관리자 지정 / 관리자 지정"""
    book = await add_library_book(session, library_a.id)
    res = await admin_client.put(f"/children/books/{book['id']}", json={"audience": "children"})
    assert res.status_code == 200
    assert (res.json()["audience"], res.json()["audience_source"]) == ("children", "manual")


async def test_manual_on_linked_book(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[features/children] 관리자 지정 (공식 서지에 연결된 도서도 지정할 수 있음)"""
    official = await add_book(session)
    book = await add_library_book(session, library_a.id, book_id=official["id"])
    res = await admin_client.put(f"/children/books/{book['id']}", json={"audience": "children"})
    assert res.status_code == 200


async def test_manual_beats_file_label(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[features/children] 관리자 지정 / 파일 근거보다 우선"""
    book = await add_library_book(session, library_a.id)
    await add_audience(session, library_a.id, book["id"], "children", "import_label")
    await admin_client.put(f"/children/books/{book['id']}", json={"audience": "general"})
    assert await _audience(admin_client, book["id"]) == ("general", "manual")


async def test_manual_rejects_kiosk(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[features/children] 관리자 지정 / 키오스크 계정 거부"""
    book = await add_library_book(session, library_a.id)
    res = await kiosk_client.put(f"/children/books/{book['id']}", json={"audience": "children"})
    assert res.status_code == 403


async def test_manual_other_library(
    admin_client: AsyncClient, session: AsyncSession, library_b: Tenant
) -> None:
    """[features/children] 관리자 지정 / 다른 기관 도서 지정"""
    theirs = await add_library_book(session, library_b.id)
    res = await admin_client.put(f"/children/books/{theirs['id']}", json={"audience": "children"})
    assert res.status_code == 404
    assert await _stored_rows(session) == 0


async def test_concurrent_manual_does_not_conflict(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[features/children] 관리자 지정 (동시 지정: 먼저 저장된 행이 있어도 충돌하지 않음)"""
    book = await add_library_book(session, library_a.id)
    await add_audience(session, library_a.id, book["id"], "children", "import_label")
    row = await session.get(LibraryBook, book["id"])
    await service._store(session, row, Audience.GENERAL, AudienceSource.MANUAL)
    assert await _audience(admin_client, book["id"]) == ("general", "manual")


async def test_automatic_evidence_does_not_replace_concurrent_manual(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[features/children] 어린이 구분 (동시에 저장돼도 낮은 근거가 관리자 지정을 덮지 않음)"""
    book = await add_library_book(session, library_a.id)
    await add_audience(session, library_a.id, book["id"], "general", "manual")
    row = await session.get(LibraryBook, book["id"])
    await service._store(session, row, Audience.CHILDREN, AudienceSource.IMPORT_LABEL)
    assert await _audience(admin_client, book["id"]) == ("general", "manual")


# --- 어린이 도서 목록 ---


async def test_list_children_only(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[features/children] 어린이 도서 목록 / 어린이 도서만 거르기"""
    kid = await add_library_book(session, library_a.id, VALID_ISBN, title="공룡 그림책")
    other = await add_library_book(session, library_a.id, VALID_ISBN_2, title="에세이")
    await add_audience(session, library_a.id, kid["id"])
    await add_audience(session, library_a.id, other["id"], "general", "manual")
    body = (await admin_client.get("/children/books")).json()
    assert [b["id"] for b in body["items"]] == [kid["id"]]
    assert body["total"] == 1
    assert body["items"][0]["title"] == "공룡 그림책"


async def test_list_excludes_other_library(
    admin_client: AsyncClient, session: AsyncSession, library_b: Tenant
) -> None:
    """[features/children] 어린이 도서 목록 / 다른 기관 도서 제외"""
    theirs = await add_library_book(session, library_b.id)
    await add_audience(session, library_b.id, theirs["id"])
    assert (await admin_client.get("/children/books")).json()["items"] == []


# --- 파일 근거 ---


@pytest.mark.parametrize(
    ("column", "value"),
    [("별치기호", "아"), ("자료실", "어린이자료실"), ("부가기호", "77810"), ("부가기호", "63710")],
)
async def test_file_label(
    admin_client_b: AsyncClient, session: AsyncSession, column: str, value: str
) -> None:
    """[features/children] 파일 근거 / 별치기호로 분류

    [features/children] 파일 근거 / 자료실로 분류
    [features/children] 파일 근거 / 부가기호로 분류
    [features/children] 파일 근거 / 초등 학습참고서 부가기호
    """
    await import_file(admin_client_b, [*HEADER, column], ["EM1", "공룡", "저자", value])
    book_id = await _imported_id(session)
    assert await _audience(admin_client_b, book_id) == ("children", "import_label")


@pytest.mark.parametrize(
    ("column", "value"),
    [("부가기호", "43810"), ("부가기호", "53710"), ("별치기호", "어"), ("별치기호", "c")],
)
async def test_not_file_label(
    admin_client_b: AsyncClient, session: AsyncSession, column: str, value: str
) -> None:
    """[features/children] 파일 근거 / 중·고등 부가기호

    [features/children] 파일 근거 / 출처가 없는 별치기호
    """
    await import_file(admin_client_b, [*HEADER, column], ["EM1", "수학", "저자", value])
    assert await _audience(admin_client_b, await _imported_id(session)) == GENERAL


async def test_label_replaces_external_category(
    library_b: Tenant, admin_client_b: AsyncClient, session: AsyncSession
) -> None:
    """[features/children] 파일 근거 / 외부 분류 근거보다 우선"""
    book = await add_library_book(session, library_b.id)
    await add_audience(session, library_b.id, book["id"], "children", "external_category")
    await import_file(
        admin_client_b, [*HEADER, "ISBN", "별치기호"], ["EM1", "책", "저자", VALID_ISBN, "아"]
    )
    assert await _audience(admin_client_b, book["id"]) == ("children", "import_label")


async def test_new_book_label_beats_external_category(
    admin_client_b: AsyncClient, session: AsyncSession
) -> None:
    """[features/children] 파일 근거 / 외부 분류 근거보다 우선 (새 도서)"""
    await add_book(session, external_category="국내도서-어린이")
    await import_file(
        admin_client_b, [*HEADER, "ISBN", "별치기호"], ["EM1", "책", "저자", VALID_ISBN, "아"]
    )
    book_id = await _imported_id(session)
    assert await _audience(admin_client_b, book_id) == ("children", "import_label")


async def test_manual_kept_on_import(
    library_b: Tenant, admin_client_b: AsyncClient, session: AsyncSession
) -> None:
    """[features/children] 파일 근거 / 관리자 지정 우선"""
    book = await add_library_book(session, library_b.id)
    await add_audience(session, library_b.id, book["id"], "general", "manual")
    await import_file(
        admin_client_b, [*HEADER, "ISBN", "별치기호"], ["EM1", "책", "저자", VALID_ISBN, "아"]
    )
    assert await _audience(admin_client_b, book["id"]) == ("general", "manual")


async def test_no_label_keeps_audience(
    library_b: Tenant, admin_client_b: AsyncClient, session: AsyncSession
) -> None:
    """[features/children] 파일 근거 / 근거가 없는 행"""
    book = await add_library_book(session, library_b.id)
    await add_audience(session, library_b.id, book["id"], "children", "import_label")
    await import_file(admin_client_b, [*HEADER, "ISBN"], ["EM1", "책", "저자", VALID_ISBN])
    assert await _audience(admin_client_b, book["id"]) == ("children", "import_label")


async def test_two_rows_same_new_book(admin_client_b: AsyncClient, session: AsyncSession) -> None:
    """[features/children] 파일 근거 (같은 새 도서의 복본 두 행도 한 번만 저장)"""
    await import_file(
        admin_client_b,
        [*HEADER, "ISBN", "별치기호"],
        ["EM1", "책", "저자", VALID_ISBN, "아"],
        ["EM2", "책", "저자", VALID_ISBN, "아"],
    )
    assert await _stored_rows(session) == 1


async def test_label_does_not_affect_other_library(
    library_a: Tenant, admin_client_b: AsyncClient, admin_client: AsyncClient, session: AsyncSession
) -> None:
    """[features/children] 파일 근거 / 다른 기관에 영향 없음"""
    theirs = await add_library_book(session, library_a.id)
    await import_file(
        admin_client_b, [*HEADER, "ISBN", "별치기호"], ["EM1", "책", "저자", VALID_ISBN, "아"]
    )
    assert await _audience(admin_client, theirs["id"]) == GENERAL


# --- 외부 분류 근거 ---


async def _link_to_category(
    client: AsyncClient, session: AsyncSession, library_id: int, category: str | None
) -> dict:
    """ISBN 없는 기관 도서에 ISBN을 채워 그 분류의 공식 서지에 연결한다."""
    await add_book(session, external_category=category)
    book = await add_library_book(session, library_id, None)
    return book


async def _fill_isbn(client: AsyncClient, book_id: int) -> None:
    res = await client.patch(f"/library-books/{book_id}", json={"isbn": VALID_ISBN})
    assert res.status_code == 200


@pytest.mark.parametrize("category", ["국내도서-유아", "국내도서-어린이", "국내도서-초등학습서"])
async def test_children_category_on_link(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant, category: str
) -> None:
    """[features/children] 외부 분류 근거 / 어린이 근거인 분류"""
    book = await _link_to_category(admin_client, session, library_a.id, category)
    await _fill_isbn(admin_client, book["id"])
    assert await _audience(admin_client, book["id"]) == ("children", "external_category")


@pytest.mark.parametrize(
    "category",
    [
        "국내도서-청소년",
        "국내도서-전집",
        "국내도서-중고등학습서-중학교",
        "국내도서-소설/시/희곡",
        None,
    ],
)
async def test_other_category_on_link(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant, category: str | None
) -> None:
    """[features/children] 외부 분류 근거 / 어린이 근거가 아닌 분류"""
    book = await _link_to_category(admin_client, session, library_a.id, category)
    await _fill_isbn(admin_client, book["id"])
    assert await _audience(admin_client, book["id"]) == GENERAL


async def test_new_book_uses_category(admin_client: AsyncClient, session: AsyncSession) -> None:
    """[features/children] 외부 분류 근거 / 새로 등록하는 도서"""
    await add_book(session, external_category="국내도서-어린이")
    created = (await admin_client.post("/library-books", json=BOOK)).json()
    assert await _audience(admin_client, created["id"]) == ("children", "external_category")


async def test_new_import_uses_category(admin_client_b: AsyncClient, session: AsyncSession) -> None:
    """[features/children] 외부 분류 근거 / 새로 가져오는 도서"""
    await add_book(session, external_category="국내도서-어린이")
    await import_file(admin_client_b, [*HEADER, "ISBN"], ["EM1", "책", "저자", VALID_ISBN])
    book_id = await _imported_id(session)
    assert await _audience(admin_client_b, book_id) == ("children", "external_category")


@pytest.mark.parametrize(
    ("audience", "source"), [("general", "manual"), ("children", "import_label")]
)
async def test_higher_evidence_kept_on_link(
    admin_client: AsyncClient,
    session: AsyncSession,
    library_a: Tenant,
    audience: str,
    source: str,
) -> None:
    """[features/children] 외부 분류 근거 / 높은 근거 유지

    [features/children] 외부 분류 근거 / 파일 근거 유지
    """
    book = await _link_to_category(admin_client, session, library_a.id, "국내도서-유아")
    await add_audience(session, library_a.id, book["id"], audience, source)
    await _fill_isbn(admin_client, book["id"])
    assert await _audience(admin_client, book["id"]) == (audience, source)


async def test_run_does_not_touch_audience(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[features/children] 외부 분류 근거 / 운영자 실행은 바꾸지 않음"""
    book = await _held(session, library_a.id)
    yes24 = FakeYes24()
    yes24.responses[VALID_ISBN] = ok(item(VALID_ISBN, goodsSortNm="국내도서-어린이"))
    await enrich(session, yes24.client())
    body = (await admin_client.get(f"/library-books/{book['id']}")).json()
    assert body["book_id"] is not None
    assert await _audience(admin_client, book["id"]) == GENERAL
    assert await _stored_rows(session) == 0


async def test_linking_existing_official_does_not_touch_audience(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[features/children] 외부 분류 근거 / 운영자 실행은 바꾸지 않음 (호출 없는 연결)"""
    await add_book(session, external_category="국내도서-어린이")
    book = await _held(session, library_a.id)
    await enrich(session, FakeYes24().client())
    assert await _audience(admin_client, book["id"]) == GENERAL


async def test_unlinking_reverts(admin_client: AsyncClient, session: AsyncSession) -> None:
    """[features/children] 외부 분류 근거 / 연결이 풀리면 되돌림"""
    await add_book(session, external_category="국내도서-어린이")
    created = (await admin_client.post("/library-books", json=BOOK)).json()
    await admin_client.patch(f"/library-books/{created['id']}", json={"isbn": VALID_ISBN_2})
    assert await _audience(admin_client, created["id"]) == GENERAL
    assert await _stored_rows(session) == 0


# --- 어린이 구분 갱신 ---


async def test_refresh_after_run(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[features/children] 어린이 구분 갱신 / 채움 뒤 갱신"""
    book = await _held(session, library_a.id)
    yes24 = FakeYes24()
    yes24.responses[VALID_ISBN] = ok(item(VALID_ISBN, goodsSortNm="국내도서-어린이"))
    await enrich(session, yes24.client())
    res = await admin_client.post("/children/refresh")
    assert res.status_code == 200
    assert res.json() == {"updated": 1}
    assert await _audience(admin_client, book["id"]) == ("children", "external_category")


@pytest.mark.parametrize(
    ("audience", "source"), [("general", "manual"), ("children", "import_label")]
)
async def test_refresh_keeps_higher_evidence(
    admin_client: AsyncClient,
    session: AsyncSession,
    library_a: Tenant,
    audience: str,
    source: str,
) -> None:
    """[features/children] 어린이 구분 갱신 / 높은 근거는 갱신하지 않음"""
    book = await _held(session, library_a.id)
    await add_audience(session, library_a.id, book["id"], audience, source)
    await enrich(session, FakeYes24().client())
    assert (await admin_client.post("/children/refresh")).json() == {"updated": 0}
    assert await _audience(admin_client, book["id"]) == (audience, source)


async def test_refresh_keeps_other_library(
    admin_client: AsyncClient,
    admin_client_b: AsyncClient,
    session: AsyncSession,
    library_a: Tenant,
    library_b: Tenant,
) -> None:
    """[features/children] 어린이 구분 갱신 / 다른 기관에 영향 없음"""
    await _held(session, library_a.id)
    theirs = await _held(session, library_b.id)
    await enrich(session, FakeYes24().client())
    await admin_client.post("/children/refresh")
    assert await _audience(admin_client_b, theirs["id"]) == GENERAL


async def test_refresh_twice(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[features/children] 어린이 구분 갱신 / 다시 갱신"""
    await _held(session, library_a.id)
    await enrich(session, FakeYes24().client())
    await admin_client.post("/children/refresh")
    assert (await admin_client.post("/children/refresh")).json() == {"updated": 0}


async def test_refresh_rejects_kiosk(kiosk_client: AsyncClient) -> None:
    """[features/children] 어린이 구분 갱신 / 키오스크 계정 거부"""
    assert (await kiosk_client.post("/children/refresh")).status_code == 403
