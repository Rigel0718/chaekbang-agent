"""개인정보 가리기. 이용자 문장을 LLM에 보내거나 저장하기 전에 코드로 가린다.

전화번호, 이메일, 주민등록번호는 정규식으로 찾는다. 하이픈 없는 13자리는 ISBN 체크 디지트가 맞으면
두고, 그 밖에 주민등록번호 형태면 가린다. 회원번호는 형식이 기관마다 달라서 그 기관의 회원번호와
맞춰 보고, `회원번호 7788`처럼 밝힌 값도 가린다. 이름은 코드로 안정적으로 찾을 수 없어 두고,
LLM으로 찾지 않는다. 가리기 전의 값이 LLM에 가게 되기 때문이다.
"""

import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.isbn import InvalidIsbnError, normalize_isbn
from app.library.models.circulation import Member

MASK = "[개인정보]"
# 이보다 짧은 회원번호는 문장 속 낱말과 맞춰 보지 않는다. `7살`의 7 같은 값을 가리지 않게 한다.
MIN_MEMBER_NUMBER_LENGTH = 4

_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_RRN_WITH_DASH = re.compile(r"(?<!\d)\d{6}\s*-\s*[1-8]\d{6}(?!\d)")
_THIRTEEN = re.compile(r"(?<!\d)\d{13}(?!\d)")
_MOBILE = re.compile(r"(?<!\d)01[016789][-.\s]?\d{3,4}[-.\s]?\d{4}(?!\d)")
_LANDLINE = re.compile(r"(?<!\d)0\d{1,2}[-.)]\s?\d{3,4}[-.]\d{4}(?!\d)")
_MEMBER_PHRASE = re.compile(
    r"(회원\s*번호|회원\s*no\.?|회원\s*카드\s*번호)(\s*(?:는|은|가|이|:|=)?\s*)([0-9A-Za-z][0-9A-Za-z-]*)",
    re.IGNORECASE,
)


def _rrn_shaped(digits: str) -> bool:
    month, day, gender = int(digits[2:4]), int(digits[4:6]), digits[6]
    return 1 <= month <= 12 and 1 <= day <= 31 and gender in "12345678"


def _thirteen(match: re.Match[str]) -> str:
    digits = match.group(0)
    try:
        normalize_isbn(digits)
        return digits
    except InvalidIsbnError:
        return MASK if _rrn_shaped(digits) else digits


def mask_patterns(text: str) -> str:
    """DB 없이 가릴 수 있는 값: 이메일, 주민등록번호, 전화번호, 밝힌 회원번호."""
    text = _EMAIL.sub(MASK, text)
    text = _RRN_WITH_DASH.sub(MASK, text)
    text = _THIRTEEN.sub(_thirteen, text)
    text = _MOBILE.sub(MASK, text)
    text = _LANDLINE.sub(MASK, text)
    return _MEMBER_PHRASE.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", text)


async def _member_numbers(session: AsyncSession, library_id: int, text: str) -> list[str]:
    rows = await session.scalars(
        select(Member.member_number).where(
            Member.library_id == library_id,
            func.length(Member.member_number) >= MIN_MEMBER_NUMBER_LENGTH,
            func.strpos(text, Member.member_number) > 0,
        )
    )
    return sorted(rows, key=len, reverse=True)


async def mask_personal(session: AsyncSession, library_id: int, text: str) -> str:
    """그 기관의 회원번호와 개인정보 형태를 `[개인정보]`로 바꾼다."""
    text = mask_patterns(text)
    for number in await _member_numbers(session, library_id, text):
        text = re.sub(
            rf"(?<![0-9A-Za-z]){re.escape(number)}(?![0-9A-Za-z])", MASK, text, flags=re.I
        )
    return text
