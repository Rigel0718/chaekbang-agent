"""[catalog/holdings-import] 적용: 도서·사본 반영, 입수 구분, 제적, 어린이 분류."""

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.catalog.import_helpers import import_file, upload
from tests.conftest import Tenant
from tests.helpers import VALID_ISBN, VALID_ISBN_2, add_book, add_holding, make_isbn

HEADER = ["등록번호", "서명", "저자"]


async def _holding(session: AsyncSession, accession: str):
    result = await session.execute(
        text(
            "SELECT h.*, b.isbn, b.title, b.publisher, b.audience, b.audience_source"
            " FROM holdings h JOIN books b ON b.id = h.book_id"
            " WHERE h.accession_number = :a"
        ),
        {"a": accession},
    )
    return result.mappings().one()


async def _book_count(session: AsyncSession) -> int:
    return await session.scalar(text("SELECT count(*) FROM books"))


# --- 미리 보기와 적용 ---


async def test_apply(admin_client_b: AsyncClient, session: AsyncSession, library_b: Tenant) -> None:
    """[catalog/holdings-import] 미리 보기와 적용 / 적용"""
    applied = await import_file(
        admin_client_b,
        [*HEADER, "ISBN", "청구기호", "자료실"],
        ["EM1", "모모", "미하엘 엔데", VALID_ISBN, "853-엔222ㅁ", "일반 자료실"],
    )
    assert applied["status"] == "applied"
    row = await _holding(session, "EM1")
    assert row["library_id"] == library_b.id
    assert (row["isbn"], row["title"]) == (VALID_ISBN, "모모")
    assert (row["call_number"], row["shelf_location"]) == ("853-엔222ㅁ", "일반 자료실")
    assert (row["status"], row["source"]) == ("available", "imported")
    assert row["last_synced_at"] is not None


async def test_apply_twice(admin_client_b: AsyncClient, session: AsyncSession) -> None:
    """[catalog/holdings-import] 미리 보기와 적용 / 두 번 적용"""
    applied = await import_file(admin_client_b, HEADER, ["EM1", "모모", "엔데"])
    res = await admin_client_b.post(f"/holding-imports/{applied['id']}/apply")
    assert res.status_code == 409
    assert await session.scalar(text("SELECT count(*) FROM holdings")) == 1


async def test_reimport_counts_only_changes(admin_client_b: AsyncClient) -> None:
    """[catalog/holdings-import] 행 분류 (다시 가져오면 바뀐 것만 update)"""
    header = [*HEADER, "청구기호"]
    await import_file(
        admin_client_b, header, ["EM1", "모모", "엔데", "A"], ["EM2", "책", "저자", "B"]
    )
    res = await upload(
        admin_client_b, header, ["EM1", "모모", "엔데", "A"], ["EM2", "책", "저자", "C"]
    )
    summary = res.json()["summary"]
    assert (summary["unchanged"], summary["update"], summary["create"]) == (1, 1, 0)


# --- 인식하지 못한 열 ---


async def test_unknown_columns_not_stored(
    admin_client_b: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/holdings-import] 인식하지 못한 열은 저장하지 않음 / 대출자 열이 있는 파일"""
    await import_file(
        admin_client_b,
        [*HEADER, "대출자", "연락처"],
        ["EM1", "모모", "엔데", "홍길순", "010-1234-5678"],
    )
    for table in ("holding_imports", "holdings", "books"):
        dump = await session.scalar(text(f"SELECT json_agg(t)::text FROM {table} t"))
        assert "홍길순" not in dump and "010-1234-5678" not in dump
        assert "대출자" not in dump


# --- 도서 찾기와 만들기 ---


async def test_existing_book_by_isbn(admin_client_b: AsyncClient, session: AsyncSession) -> None:
    """[catalog/holdings-import] 도서 찾기와 만들기 / ISBN으로 기존 도서 사용"""
    book = await add_book(session, title="모모")
    await import_file(
        admin_client_b, [*HEADER, "ISBN"], ["EM1", "모모(개정판)", "엔데", VALID_ISBN]
    )
    row = await _holding(session, "EM1")
    assert row["book_id"] == book["id"]
    assert row["title"] == "모모"
    assert await _book_count(session) == 1


async def test_reuse_book_without_isbn(admin_client_b: AsyncClient, session: AsyncSession) -> None:
    """[catalog/holdings-import] 도서 찾기와 만들기 / ISBN 없는 책의 재사용"""
    book = await add_book(session, None, title="마을 이야기", author="김주민")
    await import_file(admin_client_b, HEADER, ["EM1", "마을  이야기", "김주민"])
    assert (await _holding(session, "EM1"))["book_id"] == book["id"]
    assert await _book_count(session) == 1


async def test_fill_empty_book_fields(admin_client_b: AsyncClient, session: AsyncSession) -> None:
    """[catalog/holdings-import] 도서 찾기와 만들기 / 빈 필드 채우기"""
    await add_book(session)
    await add_book(session, VALID_ISBN_2, publisher="원래 출판사")
    await import_file(
        admin_client_b,
        [*HEADER, "ISBN", "출판사"],
        ["EM1", "책", "저자", VALID_ISBN, "비룡소"],
        ["EM2", "책", "저자", VALID_ISBN_2, "다른 출판사"],
    )
    assert (await _holding(session, "EM1"))["publisher"] == "비룡소"
    assert (await _holding(session, "EM2"))["publisher"] == "원래 출판사"


async def test_same_new_book_in_one_file(
    admin_client_b: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/holdings-import] 도서 찾기와 만들기 (같은 파일의 복본은 도서 하나)"""
    await import_file(
        admin_client_b,
        [*HEADER, "ISBN"],
        ["EM1", "모모", "엔데", VALID_ISBN],
        ["EM2", "모모", "엔데", VALID_ISBN],
        ["EM3", "마을 이야기", "김주민", ""],
        ["EM4", "마을 이야기", "김주민", ""],
    )
    assert await _book_count(session) == 2


# --- 사본 값 반영 ---


async def test_status_applied(admin_client_b: AsyncClient, session: AsyncSession) -> None:
    """[catalog/holdings-import] 사본 값 반영 / 대출 상태 반영"""
    await import_file(admin_client_b, [*HEADER, "대출상태"], ["EM1", "모모", "엔데", "대출중"])
    assert (await _holding(session, "EM1"))["status"] == "on_loan"


async def test_absent_column_keeps_value(
    admin_client_b: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/holdings-import] 사본 값 반영 / 없는 열의 기존 값 유지"""
    await import_file(admin_client_b, [*HEADER, "청구기호"], ["EM1", "모모", "엔데", "853-엔"])
    first = await _holding(session, "EM1")
    await import_file(admin_client_b, HEADER, ["EM1", "모모", "엔데"])
    second = await _holding(session, "EM1")
    assert second["call_number"] == "853-엔"
    assert second["last_synced_at"] > first["last_synced_at"]


async def test_unknown_status_keeps_state(
    admin_client_b: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/holdings-import] 사본 값 반영 / 알 수 없는 상태 표기"""
    header = [*HEADER, "대출상태"]
    await import_file(admin_client_b, header, ["EM1", "모모", "엔데", "분실"])
    applied = await import_file(admin_client_b, header, ["EM1", "모모", "엔데", "수리중"])
    assert (await _holding(session, "EM1"))["status"] == "lost"
    assert applied["summary"]["flags"] == {"unknown_status": 1}


# --- 입수 구분 인식 ---


async def test_no_acquisition_column_is_unknown(
    admin_client_b: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/holdings-import] 입수 구분 인식 / 입수 구분 열이 없는 파일"""
    await import_file(admin_client_b, [*HEADER, "가격"], ["EM1", "모모", "엔데", "9000"])
    row = await _holding(session, "EM1")
    assert (row["acquisition_type"], row["purchase_price"]) == ("unknown", None)


async def test_donated_without_donor(admin_client_b: AsyncClient, session: AsyncSession) -> None:
    """[catalog/holdings-import] 입수 구분 인식 / 기증처 없는 기증 사본"""
    applied = await import_file(
        admin_client_b, [*HEADER, "수입구분"], ["EM1", "모모", "엔데", "기증"]
    )
    assert (await _holding(session, "EM1"))["acquisition_type"] == "donated"
    assert applied["summary"]["flags"] == {}


async def test_purchased_without_isbn(admin_client_b: AsyncClient, session: AsyncSession) -> None:
    """[catalog/holdings-import] 입수 구분 인식 / ISBN 없는 매입 사본"""
    applied = await import_file(
        admin_client_b, [*HEADER, "수입구분", "가격"], ["EM1", "모모", "엔데", "구입", "9,000"]
    )
    row = await _holding(session, "EM1")
    assert (row["acquisition_type"], row["purchase_price"]) == ("purchased", 9000)
    assert applied["summary"]["flags"] == {"purchased_without_isbn": 1}
    listed = (await admin_client_b.get("/holdings", params={"incomplete": "true"})).json()
    assert listed["items"][0]["missing_fields"] == ["isbn"]


async def test_purchased_without_price(admin_client_b: AsyncClient, session: AsyncSession) -> None:
    """[catalog/holdings-import] 입수 구분 인식 / 가격 없는 매입 사본"""
    applied = await import_file(
        admin_client_b,
        [*HEADER, "ISBN", "수입구분"],
        ["EM1", "모모", "엔데", VALID_ISBN, "구입"],
    )
    row = await _holding(session, "EM1")
    assert (row["acquisition_type"], row["purchase_price"]) == ("purchased", None)
    assert applied["summary"]["flags"] == {"purchased_without_price": 1}


async def test_absent_acquisition_keeps_existing(
    admin_client_b: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/holdings-import] 사본 값 반영 / 없는 열의 기존 값 유지 (입수 구분)"""
    await import_file(
        admin_client_b,
        [*HEADER, "수입구분", "기증처"],
        ["EM1", "모모", "엔데", "기증", "주민 기증"],
    )
    await import_file(admin_client_b, HEADER, ["EM1", "모모", "엔데"])
    row = await _holding(session, "EM1")
    assert (row["acquisition_type"], row["donor"]) == ("donated", "주민 기증")


# --- 제적 ---


def _rows(count: int) -> list[list[str]]:
    return [[f"EM{n}", f"책 {n}", "저자"] for n in range(count)]


async def test_missing_row_withdrawn(admin_client_b: AsyncClient, session: AsyncSession) -> None:
    """[catalog/holdings-import] 파일에서 빠진 사본의 제적 / 빠진 사본"""
    await import_file(admin_client_b, HEADER, *_rows(3))
    res = await upload(admin_client_b, HEADER, *_rows(2))
    assert res.json()["summary"]["missing_count"] == 1
    assert (await _holding(session, "EM2"))["status"] == "available"  # 미리 보기는 그대로
    await admin_client_b.post(f"/holding-imports/{res.json()['id']}/apply")
    assert (await _holding(session, "EM2"))["status"] == "withdrawn"
    assert (await _holding(session, "EM0"))["status"] == "available"


async def test_manual_holding_kept(
    admin_client_b: AsyncClient, session: AsyncSession, library_b: Tenant
) -> None:
    """[catalog/holdings-import] 파일에서 빠진 사본의 제적 / 직접 등록 사본 유지"""
    book = await add_book(session)
    await add_holding(session, library_b.id, book["id"], "MANUAL-1")
    await import_file(admin_client_b, HEADER, *_rows(2))
    assert (await _holding(session, "MANUAL-1"))["status"] == "available"


async def test_other_library_not_withdrawn(
    admin_client_b: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/holdings-import] 파일에서 빠진 사본의 제적 (다른 기관 사본은 바뀌지 않음)"""
    book = await add_book(session)
    await add_holding(session, library_a.id, book["id"], "A-1", source="imported")
    await import_file(admin_client_b, HEADER, *_rows(1))
    assert (await _holding(session, "A-1"))["status"] == "available"


async def test_withdrawn_restored(admin_client_b: AsyncClient, session: AsyncSession) -> None:
    """[catalog/holdings-import] 파일에서 빠진 사본의 제적 / 제적 사본 복구"""
    await import_file(admin_client_b, HEADER, *_rows(3))
    await import_file(admin_client_b, HEADER, *_rows(2))
    assert (await _holding(session, "EM2"))["status"] == "withdrawn"
    await import_file(admin_client_b, HEADER, *_rows(3))
    assert (await _holding(session, "EM2"))["status"] == "available"


async def test_withdrawn_restored_with_file_status(
    admin_client_b: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/holdings-import] 파일에서 빠진 사본의 제적 / 제적 사본 복구 (파일의 상태로)"""
    await import_file(admin_client_b, HEADER, *_rows(3))
    await import_file(admin_client_b, HEADER, *_rows(2))
    header = [*HEADER, "대출상태"]
    await import_file(admin_client_b, header, *[[*r, "대출중"] for r in _rows(3)])
    assert (await _holding(session, "EM2"))["status"] == "on_loan"


async def test_mass_withdraw_needs_confirm(
    admin_client_b: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/holdings-import] 대량 제적 확인 / 확인 없는 대량 제적"""
    await import_file(admin_client_b, HEADER, *_rows(10))
    res = await upload(admin_client_b, HEADER, *_rows(4))
    apply = await admin_client_b.post(f"/holding-imports/{res.json()['id']}/apply")
    assert apply.status_code == 409
    assert "confirm_withdraw" in apply.json()["detail"]
    assert (
        await session.scalar(text("SELECT count(*) FROM holdings WHERE status = 'withdrawn'")) == 0
    )
    record = await admin_client_b.get(f"/holding-imports/{res.json()['id']}")
    assert record.json()["status"] == "preview"


async def test_mass_withdraw_confirmed(admin_client_b: AsyncClient, session: AsyncSession) -> None:
    """[catalog/holdings-import] 대량 제적 확인 / 확인한 대량 제적"""
    await import_file(admin_client_b, HEADER, *_rows(10))
    await import_file(admin_client_b, HEADER, *_rows(4), confirm_withdraw=True)
    assert (
        await session.scalar(text("SELECT count(*) FROM holdings WHERE status = 'withdrawn'")) == 6
    )


async def test_small_withdraw_no_confirm(admin_client_b: AsyncClient) -> None:
    """[catalog/holdings-import] 대량 제적 확인 (절반 미만이면 확인 없이 적용)"""
    await import_file(admin_client_b, HEADER, *_rows(10))
    applied = await import_file(admin_client_b, HEADER, *_rows(6))
    assert applied["summary"]["missing_count"] == 4


# --- 어린이 도서 분류 ---


async def _audience(session: AsyncSession, accession: str) -> tuple[str, str]:
    row = await _holding(session, accession)
    return row["audience"], row["audience_source"]


async def test_children_by_mark(admin_client_b: AsyncClient, session: AsyncSession) -> None:
    """[catalog/holdings-import] 어린이 도서 분류 근거 / 별치기호로 분류 (적용)"""
    await import_file(admin_client_b, [*HEADER, "별치기호"], ["EM1", "공룡", "저자", "아"])
    assert await _audience(session, "EM1") == ("children", "import_label")


async def test_children_by_shelf(admin_client_b: AsyncClient, session: AsyncSession) -> None:
    """[catalog/holdings-import] 어린이 도서 분류 근거 / 자료실로 분류 (적용)"""
    await import_file(admin_client_b, [*HEADER, "자료실"], ["EM1", "공룡", "저자", "어린이자료실"])
    assert await _audience(session, "EM1") == ("children", "import_label")


async def test_children_by_addition_code(
    admin_client_b: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/holdings-import] 어린이 도서 분류 근거 / 부가기호로 분류 (적용)"""
    await import_file(admin_client_b, [*HEADER, "부가기호"], ["EM1", "공룡", "저자", "77810"])
    assert await _audience(session, "EM1") == ("children", "import_label")


async def test_manual_audience_kept(admin_client_b: AsyncClient, session: AsyncSession) -> None:
    """[catalog/holdings-import] 어린이 도서 분류 근거 / 관리자 지정 우선"""
    await add_book(session, audience="general", audience_source="manual")
    await import_file(
        admin_client_b, [*HEADER, "ISBN", "별치기호"], ["EM1", "책", "저자", VALID_ISBN, "아"]
    )
    assert await _audience(session, "EM1") == ("general", "manual")


async def test_no_label_keeps_audience(admin_client_b: AsyncClient, session: AsyncSession) -> None:
    """[catalog/holdings-import] 어린이 도서 분류 근거 / 근거가 없는 행"""
    await add_book(session, audience="children", audience_source="import_label")
    await add_book(session, make_isbn(1))
    await import_file(
        admin_client_b,
        [*HEADER, "ISBN", "자료실"],
        ["EM1", "책", "저자", VALID_ISBN, "일반 자료실"],
        ["EM2", "책", "저자", make_isbn(1), "일반 자료실"],
    )
    assert await _audience(session, "EM1") == ("children", "import_label")
    assert await _audience(session, "EM2") == ("general", "default")
