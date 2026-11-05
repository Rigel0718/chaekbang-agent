"""[library/libraries] 기관 정보와 운영 방식."""

from httpx import AsyncClient

from tests.conftest import Tenant


async def test_get_own_library(kiosk_client: AsyncClient, library_a: Tenant, library_b) -> None:
    """[library/libraries] 기관 정보와 운영 방식 / 자기 기관 조회"""
    res = await kiosk_client.get("/library")
    assert res.status_code == 200
    assert res.json() == {
        "id": library_a.id,
        "name": "A 작은도서관",
        "type": "small_library",
        "loan_mode": "internal",
        "default_loan_days": 14,
    }


async def test_update_loan_days(admin_client: AsyncClient) -> None:
    """[library/libraries] 기관 정보와 운영 방식 / 기본 대출 기간 수정

    반납 예정일 계산에 쓰이는지는 tests/circulation/test_loans_api.py에서 확인한다.
    """
    res = await admin_client.patch("/library", json={"default_loan_days": 21})
    assert res.status_code == 200
    assert res.json()["default_loan_days"] == 21
    assert (await admin_client.get("/library")).json()["default_loan_days"] == 21


async def test_invalid_loan_days(admin_client: AsyncClient) -> None:
    """[library/libraries] 기관 정보와 운영 방식 / 잘못된 대출 기간"""
    res = await admin_client.patch("/library", json={"default_loan_days": 0})
    assert res.status_code == 422
    assert (await admin_client.get("/library")).json()["default_loan_days"] == 14


async def test_invalid_loan_mode(admin_client: AsyncClient) -> None:
    """[library/libraries] 기관 정보와 운영 방식 / 허용되지 않은 운영 방식"""
    res = await admin_client.patch("/library", json={"loan_mode": "hybrid"})
    assert res.status_code == 422


async def test_kiosk_cannot_update_library(kiosk_client: AsyncClient) -> None:
    """[library/staff-auth] 역할별 접근 제한 (키오스크의 기관 수정은 403)"""
    res = await kiosk_client.patch("/library", json={"default_loan_days": 7})
    assert res.status_code == 403
