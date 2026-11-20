import re
from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, BeforeValidator

from app.core.schemas import NonEmpty, PatchModel, ReadModel

_PHONE_SEPARATORS = re.compile(r"[-.\s]")
_PHONE = re.compile(r"0\d{8,10}")


def normalize_phone(value: object) -> object:
    """전화번호를 하이픈·공백·점을 지운 숫자로 맞춘다. 빈 값은 None, 형식이 틀리면 ValueError."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("전화번호는 문자열이어야 합니다")
    digits = _PHONE_SEPARATORS.sub("", value)
    if not digits:
        return None
    if not _PHONE.fullmatch(digits):
        raise ValueError("전화번호는 0으로 시작하는 9~11자리 숫자여야 합니다")
    return digits


Phone = Annotated[str | None, BeforeValidator(normalize_phone)]


class MemberCreate(BaseModel):
    """회원 정보는 회원번호, 이름, 선택 전화번호만 받는다. library_id가 있어도 쓰지 않는다."""

    member_number: NonEmpty
    name: NonEmpty
    phone: Phone = None


class MemberUpdate(PatchModel):
    NOT_NULL_FIELDS = ("name",)

    name: NonEmpty | None = None
    phone: Phone = None  # null을 주면 지운다


class MemberRead(ReadModel):
    id: int
    member_number: str
    name: str
    phone: str | None
    created_at: datetime


class LoanCreate(BaseModel):
    accession_number: NonEmpty
    member_number: NonEmpty


class LoanReturn(BaseModel):
    accession_number: NonEmpty


class LoanRead(BaseModel):
    id: int
    holding_id: int
    accession_number: str
    library_book_id: int
    title: str
    member_number: str | None  # 회원이 삭제된 반납 기록은 비어 있다
    loaned_on: date
    due_on: date
    returned_on: date | None
    overdue: bool
