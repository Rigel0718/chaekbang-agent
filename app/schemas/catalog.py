from datetime import date, datetime
from typing import Annotated, Self

from pydantic import BaseModel, Field, model_validator

from app.models.catalog import (
    AcquisitionType,
    Audience,
    AudienceSource,
    HoldingSource,
    HoldingStatus,
)
from app.schemas.common import Isbn, NonEmpty, PatchModel, ReadModel, Won

# --- 도서 (기관 공통 서지정보) ---


class BookCreate(BaseModel):
    """ISBN과 정가는 선택이다 (ISBN 없는 기증 도서, 정가를 모르는 책)."""

    isbn: Isbn | None = None
    title: NonEmpty
    author: NonEmpty
    publisher: str | None = None
    published_date: date | None = None
    list_price: Won | None = None
    kdc: str | None = None
    audience: Audience | None = None
    cover_url: str | None = None
    description: str | None = None


class BookUpdate(PatchModel):
    """요청에 포함된 필드만 바꾼다. ISBN은 null로 보내 비울 수 있다."""

    NOT_NULL_FIELDS = ("title", "author", "audience")

    isbn: Isbn | None = None
    title: NonEmpty | None = None
    author: NonEmpty | None = None
    publisher: str | None = None
    published_date: date | None = None
    list_price: Won | None = None
    kdc: str | None = None
    audience: Audience | None = None
    cover_url: str | None = None
    description: str | None = None


class BookRead(ReadModel):
    id: int
    isbn: str | None
    title: str
    author: str
    publisher: str | None
    published_date: date | None
    list_price: int | None
    kdc: str | None
    audience: Audience
    audience_source: AudienceSource
    cover_url: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime


class BookWithHoldings(BookRead):
    """로그인한 기관 기준의 소장 권수와 대출 가능 권수를 붙인 도서."""

    holding_count: int
    available_count: int


# --- 소장 사본 (기관별) ---

Price = Annotated[int, Field(ge=0, strict=True)]


def check_acquisition(
    acquisition_type: AcquisitionType, purchase_price: int | None, donor: str | None
) -> None:
    """입수 구분 규칙: 매입은 구입가 필수·기증처 없음, 기증은 구입가 없음."""
    if acquisition_type == AcquisitionType.PURCHASED:
        if purchase_price is None:
            raise ValueError("매입·납품 사본은 구입가가 필요합니다")
        if donor is not None:
            raise ValueError("매입·납품 사본에는 기증처를 둘 수 없습니다")
    elif purchase_price is not None:
        raise ValueError("기증 사본에는 구입가를 둘 수 없습니다")


class HoldingCreate(BaseModel):
    book_id: int
    accession_number: NonEmpty
    call_number: str | None = None
    shelf_location: str | None = None
    status: HoldingStatus = HoldingStatus.AVAILABLE
    acquisition_type: AcquisitionType
    purchase_price: Price | None = None
    donor: str | None = None

    @model_validator(mode="after")
    def _acquisition(self) -> Self:
        check_acquisition(self.acquisition_type, self.purchase_price, self.donor)
        return self


class HoldingUpdate(PatchModel):
    """입수 정보 규칙은 기존 값과 합친 뒤 service에서 확인한다."""

    NOT_NULL_FIELDS = ("accession_number", "status", "acquisition_type")

    accession_number: NonEmpty | None = None
    call_number: str | None = None
    shelf_location: str | None = None
    status: HoldingStatus | None = None
    acquisition_type: AcquisitionType | None = None
    purchase_price: Price | None = None
    donor: str | None = None


class HoldingRead(ReadModel):
    id: int
    book_id: int
    accession_number: str
    call_number: str | None
    shelf_location: str | None
    status: HoldingStatus
    acquisition_type: AcquisitionType
    purchase_price: int | None
    donor: str | None
    source: HoldingSource
    last_synced_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # 도서 정보
    isbn: str | None
    title: str
    author: str
