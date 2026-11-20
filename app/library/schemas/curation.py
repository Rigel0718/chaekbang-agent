"""큐레이션 요청·응답 스키마. 책 카드는 코드가 DB 값으로 만들고 이유는 큐레이션에 저장한 값이다."""

from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.library.approval import REASON_LIMIT as REJECT_REASON_LIMIT
from app.library.approval import ApprovalStatus
from app.library.models.curation import (
    INTRO_LIMIT,
    MAX_ITEMS,
    MIN_ITEMS,
    REASON_LIMIT,
    TITLE_LIMIT,
)
from app.library.schemas.librarian import BookCard


class CurationItemIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    library_book_id: int
    reason: str = Field(min_length=1, max_length=REASON_LIMIT)


class CurationWrite(BaseModel):
    """만들기와 고치기(통째로 바꿈)의 본문. 같은 책은 처음 것만 남기고, 남은 권수로 3~10을 본다.

    기관 값은 받지 않는다(토큰으로 정한다).
    """

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=TITLE_LIMIT)
    intro: str | None = Field(default=None, max_length=INTRO_LIMIT)
    items: list[CurationItemIn]

    @model_validator(mode="after")
    def _unique_items(self) -> Self:
        seen: set[int] = set()
        kept = []
        for item in self.items:
            if item.library_book_id not in seen:
                seen.add(item.library_book_id)
                kept.append(item)
        if not MIN_ITEMS <= len(kept) <= MAX_ITEMS:
            raise ValueError(f"책은 서로 다른 {MIN_ITEMS}~{MAX_ITEMS}권이어야 합니다")
        self.items = kept
        return self


class RejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=REJECT_REASON_LIMIT)


class CurationBook(BookCard):
    """큐레이션의 책 카드. `reason`은 큐레이션에 저장한 이유다."""


class CurationRead(BaseModel):
    """관리자용 큐레이션. 저장된 책을 모두 보여 주고, 지금 대출 상태를 함께 준다."""

    id: int
    title: str
    intro: str | None
    status: ApprovalStatus
    created_by: int | None
    approved_by: int | None
    approved_at: datetime | None
    published_at: datetime | None
    rejected_reason: str | None
    created_at: datetime
    updated_at: datetime
    books: list[CurationBook]


class PublishedCuration(BaseModel):
    """이용자 쪽의 게시본. 지금 추천할 수 있는 책만 담는다. 승인자·반려 사유는 없다."""

    id: int
    title: str
    intro: str | None
    published_at: datetime
    books: list[CurationBook]
