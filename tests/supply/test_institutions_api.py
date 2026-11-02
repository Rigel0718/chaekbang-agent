"""기관 REST API 테스트 (supply/institutions)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import insert

DAYCARE = {"name": "햇살어린이집", "type": "daycare"}


async def _create(client: AsyncClient, **overrides) -> dict:
    res = await client.post("/institutions", json={**DAYCARE, **overrides})
    assert res.status_code == 201, res.text
    return res.json()


async def test_create_institution(client: AsyncClient) -> None:
    """[supply/institutions] 기관 등록 / 정상 등록"""
    res = await client.post("/institutions", json={**DAYCARE, "address": "서울시"})
    assert res.status_code == 201
    body = res.json()
    assert isinstance(body["id"], int)
    assert (body["name"], body["type"], body["address"]) == ("햇살어린이집", "daycare", "서울시")


async def test_create_unknown_type(client: AsyncClient) -> None:
    """[supply/institutions] 기관 등록 / 허용되지 않은 유형"""
    res = await client.post("/institutions", json={**DAYCARE, "type": "hospital"})
    assert res.status_code == 422


@pytest.mark.parametrize("payload", [{"type": "daycare"}, {"name": "", "type": "daycare"}])
async def test_create_missing_name(client: AsyncClient, payload: dict) -> None:
    """[supply/institutions] 기관 등록 / 기관명 누락"""
    res = await client.post("/institutions", json=payload)
    assert res.status_code == 422


async def test_get_institution(client: AsyncClient) -> None:
    """[supply/institutions] 기관 조회 / 단건 조회"""
    created = await _create(client)
    res = await client.get(f"/institutions/{created['id']}")
    assert res.status_code == 200
    assert res.json()["name"] == "햇살어린이집"


async def test_get_missing_institution(client: AsyncClient) -> None:
    """[supply/institutions] 기관 조회 / 없는 기관 조회"""
    res = await client.get("/institutions/999999")
    assert res.status_code == 404


async def test_list_filter_by_type(client: AsyncClient) -> None:
    """[supply/institutions] 기관 조회 / 유형 필터"""
    await _create(client, name="한빛초등학교", type="school")
    await _create(client, name="햇살어린이집")
    await _create(client, name="달빛어린이집")
    res = await client.get("/institutions", params={"type": "daycare"})
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 2
    assert {i["type"] for i in body["items"]} == {"daycare"}


async def test_patch_contact_name(client: AsyncClient) -> None:
    """[supply/institutions] 기관 수정 / 담당자 변경"""
    created = await _create(client, contact_name="김선생", phone="02-000-0000")
    res = await client.patch(f"/institutions/{created['id']}", json={"contact_name": "박선생"})
    assert res.status_code == 200
    body = res.json()
    assert body["contact_name"] == "박선생"
    assert (body["name"], body["phone"]) == ("햇살어린이집", "02-000-0000")


async def test_delete_institution(client: AsyncClient) -> None:
    """[supply/institutions] 기관 삭제 / 참조 없는 기관 삭제"""
    created = await _create(client)
    res = await client.delete(f"/institutions/{created['id']}")
    assert res.status_code == 204
    assert (await client.get(f"/institutions/{created['id']}")).status_code == 404


async def test_delete_institution_with_order_list(
    client: AsyncClient, session: AsyncSession
) -> None:
    """[supply/institutions] 기관 삭제 / 주문 목록이 있는 기관 삭제"""
    created = await _create(client)
    await insert(
        session, "institution_orders", institution_id=created["id"], source_filename="a.xlsx"
    )
    res = await client.delete(f"/institutions/{created['id']}")
    assert res.status_code == 409
    assert (await client.get(f"/institutions/{created['id']}")).status_code == 200
