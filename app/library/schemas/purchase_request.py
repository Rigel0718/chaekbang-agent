"""구매 요청서의 요청·응답 스키마. 기관 값은 받지 않는다(토큰으로 정한다). 회원 값은 어디에도 없다.

금액은 int(원)이다. 확정 전 응답의 단가·금액·추정 총액은 그때 조회한 정가로 계산한 값이고 저장하지
않는다. 확정본은 확정 때 기록한 값을 그대로 돌려준다.
"""

from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.core.schemas import Isbn, ReadModel, Won
from app.library.approval import ApprovalStatus
from app.library.models.purchase_request import (
    ITEM_AUTHOR_LIMIT,
    ITEM_TITLE_LIMIT,
    MAX_ITEMS,
    MAX_QUANTITY,
    MIN_ITEMS,
    MIN_QUANTITY,
    NOTE_LIMIT,
    REASON_LIMIT,
    TITLE_LIMIT,
    VENDOR_LIMIT,
    PriceSource,
    ReasonKind,
)
from app.library.schemas.curation import RejectRequest

__all__ = [
    "ItemIn",
    "ItemRead",
    "PriceEstimate",
    "PurchaseRequestDetail",
    "PurchaseRequestRead",
    "PurchaseRequestWrite",
    "RejectRequest",
]

Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=TITLE_LIMIT)
]
ItemTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=ITEM_TITLE_LIMIT)
]


def _blank_to_none(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value.strip()


class ItemIn(BaseModel):
    """요청서 항목. ISBN으로 식별한다. 서명·저자는 REST에서 관리자가 적는다(tool은 코드가 채움)."""

    model_config = ConfigDict(extra="forbid")

    isbn: Isbn
    title: ItemTitle
    author: Annotated[str | None, Field(max_length=ITEM_AUTHOR_LIMIT)] = None
    quantity: int = Field(ge=MIN_QUANTITY, le=MAX_QUANTITY, strict=True)
    reason_kind: ReasonKind
    reason: Annotated[str | None, Field(max_length=REASON_LIMIT)] = None

    @model_validator(mode="after")
    def _blank_optional(self) -> Self:
        self.author = _blank_to_none(self.author)
        self.reason = _blank_to_none(self.reason)
        return self


class PurchaseRequestWrite(BaseModel):
    """만들기와 고치기(통째로 바꿈)의 본문. 같은 ISBN을 두 번 넣으면 거부한다."""

    model_config = ConfigDict(extra="forbid")

    title: Title
    vendor_name: Annotated[str | None, Field(max_length=VENDOR_LIMIT)] = None
    note: Annotated[str | None, Field(max_length=NOTE_LIMIT)] = None
    items: Annotated[list[ItemIn], Field(min_length=MIN_ITEMS, max_length=MAX_ITEMS)]

    @model_validator(mode="after")
    def _check(self) -> Self:
        self.vendor_name = _blank_to_none(self.vendor_name)
        self.note = _blank_to_none(self.note)
        isbns = [item.isbn for item in self.items]
        if len(set(isbns)) != len(isbns):
            raise ValueError("같은 ISBN을 두 번 넣을 수 없습니다. 권수를 늘려 주세요")
        return self


class ItemRead(ReadModel):
    isbn: str
    title: str
    author: str | None
    quantity: int
    reason_kind: ReasonKind
    reason: str | None
    unit_price: Won | None  # 확정본은 기록한 값, 확정 전 상세는 조회한 정가(저장하지 않음)
    amount: Won | None


class PurchaseRequestRead(BaseModel):
    """목록 줄. 정가를 조회하지 않아서 금액은 확정본에만 있다."""

    id: int
    title: str
    vendor_name: str | None
    note: str | None
    status: ApprovalStatus
    item_count: int
    created_by: int | None
    approved_by: int | None
    approved_at: datetime | None
    confirmed_at: datetime | None
    rejected_reason: str | None
    total_amount: Won | None
    priced_at: datetime | None
    price_source: PriceSource | None
    created_at: datetime
    updated_at: datetime


class PriceEstimate(BaseModel):
    """확정 전 상세의 추정 금액. 요청할 때마다 새로 조회하고 저장하지 않는다."""

    estimated_total: Won | None  # 가격을 찾은 항목 금액의 합. 조회할 수 없었으면 None
    missing_price_count: int
    priced_at: datetime | None
    unavailable: bool  # 정가 조회를 쓸 수 없었다


class PurchaseRequestDetail(PurchaseRequestRead):
    items: list[ItemRead]
    estimate: PriceEstimate | None  # 확정본은 None(기록한 금액을 쓴다)
