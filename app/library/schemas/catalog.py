from datetime import date, datetime
from typing import Annotated, Any, Self

from pydantic import BaseModel, Field, model_validator

from app.central.models import ExternalSource
from app.core.schemas import Isbn, NonEmpty, PatchModel, ReadModel, Won
from app.library.models.catalog import (
    BIBLIOGRAPHIC_FIELDS,
    OFFICIAL_ONLY_FIELDS,
    AcquisitionType,
    EnrichmentStatus,
    HoldingSource,
    HoldingStatus,
    LibraryBook,
)

# --- 기관 도서 ---


class LibraryBookCreate(BaseModel):
    """ISBN과 정가는 선택이다 (ISBN 없는 기증 도서, 정가를 모르는 책)."""

    isbn: Isbn | None = None
    title: NonEmpty
    author: NonEmpty
    publisher: str | None = None
    published_date: date | None = None
    list_price: Won | None = None
    kdc: str | None = None
    cover_url: str | None = None
    description: str | None = None


class LibraryBookUpdate(PatchModel):
    """요청에 포함된 필드만 바꾼다. ISBN은 null로 보내 비울 수 있다."""

    NOT_NULL_FIELDS = ("title", "author")

    isbn: Isbn | None = None
    title: NonEmpty | None = None
    author: NonEmpty | None = None
    publisher: str | None = None
    published_date: date | None = None
    list_price: Won | None = None
    kdc: str | None = None
    cover_url: str | None = None
    description: str | None = None


class LibraryBookRead(ReadModel):
    """서지 필드는 표시 값이다. book_id가 있으면 공식 서지의 값을 먼저 쓴다."""

    id: int
    book_id: int | None
    isbn: str | None
    title: str
    author: str
    publisher: str | None
    published_date: date | None
    list_price: int | None
    kdc: str | None
    cover_url: str | None
    description: str | None
    enrichment_status: EnrichmentStatus
    enrichment_checked_at: datetime | None
    created_at: datetime
    updated_at: datetime
    # 공식 서지에만 있는 값. 연결이 없으면 비어 있다
    subtitle: str | None
    table_of_contents: str | None
    series_name: str | None
    external_source: ExternalSource | None
    external_url: str | None
    external_category: str | None

    @classmethod
    def of(cls, library_book: LibraryBook) -> dict[str, Any]:
        """기관 도서를 표시 값이 채워진 응답 값으로 바꾼다."""
        book = library_book.book
        own = set(LibraryBookRead.model_fields) - set(OFFICIAL_ONLY_FIELDS)
        return (
            {f: getattr(library_book, f) for f in own}
            | {f: library_book.shown(f) for f in BIBLIOGRAPHIC_FIELDS}
            | {f: getattr(book, f) if book is not None else None for f in OFFICIAL_ONLY_FIELDS}
        )


class LibraryBookWithHoldings(LibraryBookRead):
    """소장 권수와 대출 가능 권수를 붙인 기관 도서."""

    holding_count: int
    available_count: int


class EnrichmentCounts(BaseModel):
    """로그인한 기관의 소장 도서를 처리 상태별로 센 건수."""

    pending: int = 0
    enriched: int = 0
    not_found: int = 0
    mismatch: int = 0
    no_isbn: int = 0


# --- 소장 사본 (기관별) ---

Price = Annotated[int, Field(ge=0, strict=True)]


def check_acquisition(
    acquisition_type: AcquisitionType,
    purchase_price: int | None,
    donor: str | None,
    *,
    imported_purchase: bool = False,
) -> None:
    """입수 구분 규칙: 매입은 구입가 필수·기증처 없음, 기증은 구입가 없음, 모름은 둘 다 없음.

    imported_purchase=True면 이미 매입인 가져온 사본이라 구입가가 없어도 된다.
    """
    if acquisition_type == AcquisitionType.PURCHASED:
        if purchase_price is None and not imported_purchase:
            raise ValueError("매입·납품 사본은 구입가가 필요합니다")
        if donor is not None:
            raise ValueError("매입·납품 사본에는 기증처를 둘 수 없습니다")
    elif purchase_price is not None:
        raise ValueError("기증이나 입수 구분을 모르는 사본에는 구입가를 둘 수 없습니다")
    elif acquisition_type == AcquisitionType.UNKNOWN and donor is not None:
        raise ValueError("기증처가 있으면 입수 구분을 기증으로 지정하세요")


class HoldingCreate(BaseModel):
    library_book_id: int
    accession_number: NonEmpty
    call_number: str | None = None
    shelf_location: str | None = None
    status: HoldingStatus = HoldingStatus.AVAILABLE
    acquisition_type: AcquisitionType
    purchase_price: Price | None = None
    donor: str | None = None

    @model_validator(mode="after")
    def _acquisition(self) -> Self:
        if self.acquisition_type == AcquisitionType.UNKNOWN:
            raise ValueError("직접 등록할 때는 입수 구분을 매입이나 기증으로 지정하세요")
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
    library_book_id: int
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
    # 매입 사본에 빠진 정보 (isbn, purchase_price). 저장하지 않고 조회할 때 계산한다
    missing_fields: list[str]
