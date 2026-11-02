"""기관 service 단위 테스트 (supply/institutions)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supply import InstitutionType
from app.schemas.supply import InstitutionCreate, InstitutionUpdate
from app.services.errors import ConflictError, NotFoundError
from app.services.supply import institutions
from tests.helpers import insert


def _create(name: str = "햇살어린이집", type: str = "daycare", **extra) -> InstitutionCreate:
    return InstitutionCreate(name=name, type=type, **extra)


async def test_create_and_get(session: AsyncSession) -> None:
    """[supply/institutions] 기관 등록 / 정상 등록"""
    created = await institutions.create_institution(session, _create(contact_name="김선생"))
    assert created.id is not None
    fetched = await institutions.get_institution(session, created.id)
    assert (fetched.name, fetched.type, fetched.contact_name) == (
        "햇살어린이집",
        InstitutionType.DAYCARE,
        "김선생",
    )


async def test_get_missing(session: AsyncSession) -> None:
    """[supply/institutions] 기관 조회 / 없는 기관 조회"""
    with pytest.raises(NotFoundError):
        await institutions.get_institution(session, 999_999)


async def test_list_filters_by_type(session: AsyncSession) -> None:
    """[supply/institutions] 기관 조회 / 유형 필터"""
    await institutions.create_institution(session, _create("한빛초등학교", "school"))
    await institutions.create_institution(session, _create("햇살어린이집", "daycare"))
    await institutions.create_institution(session, _create("달빛어린이집", "daycare"))
    items, total = await institutions.list_institutions(
        session, limit=20, offset=0, type=InstitutionType.DAYCARE
    )
    assert total == 2
    assert {i.name for i in items} == {"햇살어린이집", "달빛어린이집"}


async def test_update_contact_only(session: AsyncSession) -> None:
    """[supply/institutions] 기관 수정 / 담당자 변경"""
    created = await institutions.create_institution(session, _create(phone="02-000-0000"))
    updated = await institutions.update_institution(
        session, created.id, InstitutionUpdate(contact_name="박선생")
    )
    assert (updated.contact_name, updated.phone, updated.name) == (
        "박선생",
        "02-000-0000",
        "햇살어린이집",
    )


async def test_delete_with_order_list(session: AsyncSession) -> None:
    """[supply/institutions] 기관 삭제 / 주문 목록이 있는 기관 삭제"""
    created = await institutions.create_institution(session, _create())
    await insert(session, "institution_orders", institution_id=created.id, source_filename="a.xlsx")
    with pytest.raises(ConflictError):
        await institutions.delete_institution(session, created.id)


async def test_delete_with_quote_draft(session: AsyncSession) -> None:
    """[supply/institutions] 기관 삭제 (견적서가 참조하는 기관)"""
    created = await institutions.create_institution(session, _create())
    await insert(
        session, "quote_drafts", institution_id=created.id, subtotal=0, discount_amount=0, total=0
    )
    with pytest.raises(ConflictError):
        await institutions.delete_institution(session, created.id)


async def test_delete(session: AsyncSession) -> None:
    """[supply/institutions] 기관 삭제 / 참조 없는 기관 삭제"""
    created = await institutions.create_institution(session, _create())
    await institutions.delete_institution(session, created.id)
    with pytest.raises(NotFoundError):
        await institutions.get_institution(session, created.id)
