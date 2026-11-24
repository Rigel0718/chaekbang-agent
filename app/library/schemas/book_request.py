"""희망도서 스키마. 키오스크 응답에는 회원 값이 없고, 관리자 목록에만 회원번호가 있다."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, BeforeValidator, StringConstraints

from app.core.schemas import Isbn, ReadModel
from app.library.models.book_request import AUTHOR_LIMIT, TITLE_LIMIT, BookRequestStatus

Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_LIMIT)
]
Author = Annotated[str, StringConstraints(strip_whitespace=True, max_length=AUTHOR_LIMIT)]


def _blank_to_none(value: object) -> object:
    """빈 저자·ISBN은 없음(None)으로 본다."""
    if isinstance(value, str) and not value.strip():
        return None
    return value


class BookRequestCreate(BaseModel):
    """기관은 직원 토큰, 신청 회원은 회원 세션이 정한다. 보낸 member_number는 무시한다."""

    title: Title
    author: Annotated[Author | None, BeforeValidator(_blank_to_none)] = None
    isbn: Annotated[Isbn | None, BeforeValidator(_blank_to_none)] = None


class BookRequestRead(ReadModel):
    id: int
    title: str
    author: str | None
    isbn: str | None
    status: BookRequestStatus
    created_at: datetime


class BookRequestAdminRead(BookRequestRead):
    member_number: str | None  # 회원이 지워졌으면 None
    closed_at: datetime | None
    # 구매 요청서를 확정해서 닫힌 신청만 값이 있다(관리자가 닫았거나 처리 전이면 None)
    purchase_request_id: int | None


class BookRequestUpdate(BaseModel):
    """닫기만 한다. `requested`로 되돌리지 않는다."""

    status: Literal[BookRequestStatus.CLOSED]
