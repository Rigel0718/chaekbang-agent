from datetime import date, datetime

from pydantic import BaseModel

from app.core.schemas import NonEmpty, PatchModel, ReadModel


class MemberCreate(BaseModel):
    """회원 정보는 회원번호와 이름만 받는다. 요청에 library_id가 있어도 쓰지 않는다."""

    member_number: NonEmpty
    name: NonEmpty


class MemberUpdate(PatchModel):
    NOT_NULL_FIELDS = ("name",)

    name: NonEmpty | None = None


class MemberRead(ReadModel):
    id: int
    member_number: str
    name: str
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
