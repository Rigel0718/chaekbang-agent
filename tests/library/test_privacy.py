"""[agent/chat-sessions] 개인정보 가리기. LLM에 가는 문장과 저장 문장은 대화 API 테스트에서 본다."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.library.privacy import MASK, mask_patterns, mask_personal
from tests.conftest import Tenant
from tests.helpers import VALID_ISBN, VALID_ISBN_2, add_member


@pytest.mark.parametrize(
    "phone", ["010-1234-5678", "01012345678", "010 1234 5678", "02-123-4567", "031-1234-5678"]
)
def test_phone(phone: str) -> None:
    """[agent/chat-sessions] 개인정보 가리기 / 전화번호"""
    masked = mask_patterns(f"연락처는 {phone}이에요")
    assert phone not in masked
    assert MASK in masked


def test_email_and_rrn() -> None:
    """[agent/chat-sessions] 개인정보 가리기 / 이메일과 주민등록번호"""
    text = "메일 reader.kim+1@example.co.kr 주민번호 900101-1234567, 9001012234567"
    masked = mask_patterns(text)
    for value in ("reader.kim+1@example.co.kr", "900101-1234567", "9001012234567"):
        assert value not in masked
    assert masked.count(MASK) == 3


async def test_member_number(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/chat-sessions] 개인정보 가리기 / 그 기관의 회원번호"""
    await add_member(session, library_a.id, "A-2024-0042")
    await add_member(session, library_a.id, "7")
    masked = await mask_personal(session, library_a.id, "제 번호는 A-2024-0042이고 7살 아이요")
    assert "A-2024-0042" not in masked
    assert "7살" in masked


async def test_member_number_other_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[agent/chat-sessions] 개인정보 가리기 / 그 기관의 회원번호 (다른 기관 번호는 안 봄)"""
    await add_member(session, library_b.id, "B-5555")
    masked = await mask_personal(session, library_a.id, "B-5555 책")
    assert masked == "B-5555 책"


@pytest.mark.parametrize(
    "text", ["회원번호 7788 대출", "회원 번호는 7788", "회원번호:7788", "회원번호가 AB12"]
)
async def test_stated_member_number(session: AsyncSession, library_a: Tenant, text: str) -> None:
    """[agent/chat-sessions] 개인정보 가리기 / 회원번호라고 쓴 값"""
    masked = await mask_personal(session, library_a.id, text)
    assert "7788" not in masked and "AB12" not in masked
    assert MASK in masked


async def test_isbn_call_number_year_kept(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/chat-sessions] 개인정보 가리기 / ISBN은 유지"""
    text = f"{VALID_ISBN} 책과 978-89-{VALID_ISBN_2[5:]} 청구기호 813.7-한232ㅊ, 2024년 책"
    assert await mask_personal(session, library_a.id, text) == text
