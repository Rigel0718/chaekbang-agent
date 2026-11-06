"""[catalog/holdings-import] 업로드, 미리 보기, 기록 조회."""

import json

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
    assert await _count(session, "books") == 0


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
    # 적용은 자체 대출 기관이면 409가 먼저다. 같은 가져오기 기관끼리는 404다.
    await session.execute(
        text("UPDATE libraries SET loan_mode = 'imported' WHERE id = :id"), {"id": library_a.id}
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
