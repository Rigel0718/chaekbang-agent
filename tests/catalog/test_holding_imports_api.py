"""[catalog/holdings-import] 업로드, 미리 보기, 기록 조회."""

import json
import re
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.library.schemas.holding_imports import HoldingImportRow
from tests.catalog.import_helpers import csv_bytes, import_file, upload
from tests.conftest import Tenant
from tests.helpers import VALID_ISBN

HEADER = ["등록번호", "서명", "저자"]


async def _count(session: AsyncSession, table: str) -> int:
    return await session.scalar(text(f"SELECT count(*) FROM {table}"))


async def test_internal_library_rejected(admin_client: AsyncClient, session: AsyncSession) -> None:
    """[catalog/holdings-import] 가져오기 대상과 권한 / 자체 대출 기관의 가져오기"""
    res = await upload(admin_client, HEADER, ["EM1", "모모", "엔데"])
    assert res.status_code == 409
    assert await _count(session, "holding_imports") == 0


async def test_kiosk_rejected(kiosk_client_b: AsyncClient) -> None:
    """[catalog/holdings-import] 가져오기 대상과 권한 / 키오스크의 가져오기"""
    res = await upload(kiosk_client_b, HEADER, ["EM1", "모모", "엔데"])
    assert res.status_code == 403
    assert (await kiosk_client_b.get("/holding-imports")).status_code == 403


async def test_preview_does_not_change_holdings(
    admin_client_b: AsyncClient, session: AsyncSession
) -> None:
    """[catalog/holdings-import] 미리 보기와 적용 / 미리 보기는 장서를 바꾸지 않음"""
    res = await upload(
        admin_client_b,
        [*HEADER, "ISBN"],
        ["EM1", "모모", "엔데", VALID_ISBN],
        ["EM2", "마을 이야기", "김주민", ""],
    )
    assert res.status_code == 201
    body = res.json()
    assert body["status"] == "preview"
    assert body["summary"]["create"] == 2
    assert body["summary"]["missing_count"] == 0
    assert body["column_mapping"]["title"] == "서명"
    assert await _count(session, "holdings") == 0
    assert await _count(session, "library_books") == 0


async def test_missing_required_column_response(admin_client_b: AsyncClient) -> None:
    """[catalog/holdings-import] 필수 열과 머리글 인식 / 필수 열 없음 (응답)"""
    res = await upload(admin_client_b, ["등록번호", "서명", "비고"], ["EM1", "모모", ""])
    assert res.status_code == 422
    assert res.json()["missing"] == ["저자"]
    assert res.json()["headers"] == ["등록번호", "서명", "비고"]


async def test_unsupported_file_response(admin_client_b: AsyncClient) -> None:
    """[catalog/holdings-import] 파일 형식 / 지원하지 않는 형식 (응답)"""
    files = {"file": ("old.xls", b"\xd0\xcf\x11\xe0" + b"\x00" * 32, "application/vnd.ms-excel")}
    res = await admin_client_b.post("/holding-imports", files=files)
    assert res.status_code == 422
    assert "xlsx나 CSV" in res.json()["detail"]


async def test_cp949_upload(admin_client_b: AsyncClient) -> None:
    """[catalog/holdings-import] 파일 형식 / CP949 CSV (업로드)"""
    content = csv_bytes(HEADER, ["EM1", "마당을 나온 암탉", "황선미"], encoding="cp949")
    res = await admin_client_b.post(
        "/holding-imports", files={"file": ("a.csv", content, "text/csv")}
    )
    rows = await admin_client_b.get(f"/holding-imports/{res.json()['id']}/rows")
    assert rows.json()["items"][0]["title"] == "마당을 나온 암탉"


async def test_column_mapping_form(admin_client_b: AsyncClient) -> None:
    """[catalog/holdings-import] 열 직접 지정 / 인식하지 못한 머리글 지정 (업로드)"""
    rows = (["등록번호", "서명", "책임표시"], ["EM1", "모모", "엔데"])
    assert (await upload(admin_client_b, *rows)).status_code == 422
    res = await upload(admin_client_b, *rows, column_mapping=json.dumps({"author": "책임표시"}))
    assert res.status_code == 201
    assert res.json()["column_mapping"]["author"] == "책임표시"


async def test_bad_column_mapping(admin_client_b: AsyncClient) -> None:
    """[catalog/holdings-import] 열 직접 지정 (형식이 틀린 매핑)"""
    res = await upload(admin_client_b, HEADER, ["EM1", "모모", "엔데"], column_mapping="[1]")
    assert res.status_code == 422


async def test_skipped_rows_keep_others(admin_client_b: AsyncClient) -> None:
    """[catalog/holdings-import] 행 분류 / 저자가 빈 행 (미리 보기 건수와 사유)"""
    res = await upload(admin_client_b, HEADER, ["EM1", "모모", ""], ["EM2", "모모", "엔데"])
    summary = res.json()["summary"]
    assert (summary["skipped"], summary["create"]) == (1, 1)
    rows = await admin_client_b.get(
        f"/holding-imports/{res.json()['id']}/rows", params={"outcome": "skipped"}
    )
    assert "저자" in rows.json()["items"][0]["skip_reason"]


async def test_rows_filter_by_flag(admin_client_b: AsyncClient) -> None:
    """[catalog/holdings-import] 가져오기 기록 조회 / 표기된 행만 보기"""
    res = await upload(
        admin_client_b,
        [*HEADER, "수입구분", "가격"],
        ["EM1", "모모", "엔데", "구입", "9000"],
        ["EM2", "모모", "엔데", "기증", ""],
    )
    assert res.json()["summary"]["flags"] == {"purchased_without_isbn": 1}
    rows = await admin_client_b.get(
        f"/holding-imports/{res.json()['id']}/rows", params={"flag": "purchased_without_isbn"}
    )
    assert [r["accession_number"] for r in rows.json()["items"]] == ["EM1"]


async def test_other_library_record_is_404(
    admin_client: AsyncClient,
    admin_client_b: AsyncClient,
    session: AsyncSession,
    library_a: Tenant,
) -> None:
    """[catalog/holdings-import] 가져오기 기록 조회 / 다른 기관의 기록"""
    record = (await upload(admin_client_b, HEADER, ["EM1", "모모", "엔데"])).json()
    url = f"/holding-imports/{record['id']}"
    assert (await admin_client.get(url)).status_code == 404
    assert (await admin_client.get(f"{url}/rows")).status_code == 404
    assert (await admin_client.get("/holding-imports")).json()["total"] == 0
    # 적용은 자체 대출 기관이면 409가 먼저다. 같은 외부 대출 기관끼리는 404다.
    await session.execute(
        text("UPDATE libraries SET loan_mode = 'external' WHERE id = :id"), {"id": library_a.id}
    )
    assert (await admin_client.post(f"{url}/apply")).status_code == 404
    assert (await admin_client_b.get(url)).json()["status"] == "preview"


async def test_list_records(admin_client_b: AsyncClient) -> None:
    """[catalog/holdings-import] 가져오기 기록 조회 (목록과 단건)"""
    applied = await import_file(admin_client_b, HEADER, ["EM1", "모모", "엔데"])
    listed = (await admin_client_b.get("/holding-imports")).json()
    assert [r["id"] for r in listed["items"]] == [applied["id"]]
    assert listed["items"][0]["status"] == "applied"
    assert applied["applied_at"] is not None


# 행 응답에 기증처를 넣지 않는다. 필드를 더하면 이 목록이 실패하므로 개인정보가 아닌지 보고 넣는다.
ROW_FIELDS = {
    "row_no",
    "outcome",
    "skip_reason",
    "flags",
    "accession_number",
    "title",
    "author",
    "isbn",
    "status",
    "acquisition",
}


def test_row_schema_fields_are_fixed() -> None:
    """[catalog/holdings-import] 가져오기 기록 조회: 행 응답 필드는 정해진 목록, 기증처 없음."""
    assert set(HoldingImportRow.model_fields) == ROW_FIELDS


async def test_rows_have_no_donor(admin_client_b: AsyncClient, session: AsyncSession) -> None:
    """[catalog/holdings-import] 가져오기 기록 조회 / 행 응답에 기증처 없음"""
    res = await upload(
        admin_client_b,
        [*HEADER, "수입구분", "기증처"],
        ["EM1", "모모", "엔데", "기증", "기증자홍길동"],
    )
    assert res.status_code == 201, res.text
    import_id = res.json()["id"]
    # 기증처는 기록에는 저장된다(적용 때 쓴다). 응답에서만 빠져야 한다.
    stored = await session.scalar(
        text("SELECT rows -> 0 ->> 'donor' FROM holding_imports WHERE id = :id"), {"id": import_id}
    )
    assert stored == "기증자홍길동"
    for params in ({}, {"outcome": "create"}):
        rows = await admin_client_b.get(f"/holding-imports/{import_id}/rows", params=params)
        items = rows.json()["items"]
        assert items and all(set(item) == ROW_FIELDS for item in items)
        assert "기증자홍길동" not in rows.text
    assert "기증자홍길동" not in (await admin_client_b.get(f"/holding-imports/{import_id}")).text
    assert "기증자홍길동" not in (await admin_client_b.get("/holding-imports")).text


IMPORTS_JS = Path(__file__).resolve().parents[2] / "app/web/public/admin/imports.js"


async def test_mass_withdraw_message_has_screen_mark(admin_client_b: AsyncClient) -> None:
    """[web-ui] 대량 제적 응답의 구분: 화면이 보는 낱말은 대량 제적 409에만 있다."""
    mark = re.search(r'MASS_WITHDRAW_MARK = "(\w+)"', IMPORTS_JS.read_text(encoding="utf-8"))[1]
    books = [[f"EM{i}", f"책{i}", "저자"] for i in range(1, 5)]
    applied = await import_file(admin_client_b, HEADER, *books)

    again = await admin_client_b.post(f"/holding-imports/{applied['id']}/apply")
    assert again.status_code == 409 and mark not in again.json()["detail"]

    partial = await upload(admin_client_b, HEADER, books[0])
    res = await admin_client_b.post(f"/holding-imports/{partial.json()['id']}/apply")
    assert res.status_code == 409 and mark in res.json()["detail"]


async def test_delete_preview(admin_client_b: AsyncClient, session: AsyncSession) -> None:
    """[catalog/holdings-import] 미리 보기 삭제 / 미리 보기 지우기"""
    await import_file(admin_client_b, HEADER, ["EM1", "모모", "엔데"])
    preview = (await upload(admin_client_b, HEADER, ["EM2", "데미안", "헤세"])).json()
    holdings = await _count(session, "holdings")
    url = f"/holding-imports/{preview['id']}"

    res = await admin_client_b.delete(url)
    assert res.status_code == 204, res.text
    assert (await admin_client_b.get(url)).status_code == 404
    listed = (await admin_client_b.get("/holding-imports")).json()
    assert preview["id"] not in [r["id"] for r in listed["items"]] and listed["total"] == 1
    assert await _count(session, "holdings") == holdings
    assert (await admin_client_b.delete(url)).status_code == 404


async def test_delete_applied_rejected(admin_client_b: AsyncClient) -> None:
    """[catalog/holdings-import] 미리 보기 삭제 / 적용한 기록"""
    applied = await import_file(admin_client_b, HEADER, ["EM1", "모모", "엔데"])
    url = f"/holding-imports/{applied['id']}"
    assert (await admin_client_b.delete(url)).status_code == 409
    assert (await admin_client_b.get(url)).json()["status"] == "applied"


async def test_delete_scope_and_roles(
    admin_client: AsyncClient,
    admin_client_b: AsyncClient,
    kiosk_client_b: AsyncClient,
    session: AsyncSession,
    library_a: Tenant,
) -> None:
    """[catalog/holdings-import] 미리 보기 삭제 / 다른 기관과 권한"""
    record = (await upload(admin_client_b, HEADER, ["EM1", "모모", "엔데"])).json()
    url = f"/holding-imports/{record['id']}"
    assert (await kiosk_client_b.delete(url)).status_code == 403
    assert (await admin_client.delete(url)).status_code == 409  # 자체 대출 기관
    await session.execute(
        text("UPDATE libraries SET loan_mode = 'external' WHERE id = :id"), {"id": library_a.id}
    )
    assert (await admin_client.delete(url)).status_code == 404  # 다른 기관의 기록
    assert (await admin_client_b.get(url)).json()["status"] == "preview"
