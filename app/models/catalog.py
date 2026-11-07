"""공식 서지(기관 공통), 기관 도서와 소장 사본(기관별)."""

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import ISBN_PATTERN, Base, TimestampMixin, str_enum

# 공식 서지와 기관 도서가 함께 가진 서지 필드. 연결된 도서는 공식 값을 먼저 보여 준다.
BIBLIOGRAPHIC_FIELDS = (
    "title",
    "author",
    "publisher",
    "published_date",
    "list_price",
    "kdc",
    "cover_url",
    "description",
)
# 공식 서지에만 있는 필드. 기관은 입력하지 않고, 연결되면 조회 응답에 나온다.
OFFICIAL_ONLY_FIELDS = (
    "subtitle",
    "table_of_contents",
    "series_name",
    "external_source",
    "external_url",
    "external_category",
)


class Audience(StrEnum):
    CHILDREN = "children"
    GENERAL = "general"


class AudienceSource(StrEnum):
    DEFAULT = "default"  # 근거 없음
    MANUAL = "manual"  # 관리자 지정
    IMPORT_LABEL = "import_label"  # 가져온 파일의 별치기호·자료실·부가기호
    EXTERNAL_CATEGORY = "external_category"  # 연결된 공식 서지의 분류 원문


class ExternalSource(StrEnum):
    YES24 = "yes24"


class EnrichmentStatus(StrEnum):
    PENDING = "pending"  # 공식 서지 채움 대기
    ENRICHED = "enriched"  # 공식 서지에 연결됨
    NOT_FOUND = "not_found"  # 외부 API에서 찾지 못함
    MISMATCH = "mismatch"  # 응답의 ISBN이 요청과 다름


class HoldingStatus(StrEnum):
    AVAILABLE = "available"
    ON_LOAN = "on_loan"
    LOST = "lost"
    DAMAGED = "damaged"
    WITHDRAWN = "withdrawn"  # 제적: 가져온 파일에서 빠졌거나 관리자가 뺀 사본


class AcquisitionType(StrEnum):
    PURCHASED = "purchased"  # 매입·공식 납품
    DONATED = "donated"  # 기증
    UNKNOWN = "unknown"  # 알 수 없음 (장서 가져오기에서만 생긴다)


class HoldingSource(StrEnum):
    MANUAL = "manual"
    IMPORTED = "imported"


class ImportStatus(StrEnum):
    PREVIEW = "preview"  # 미리 보기만 만들었다. 장서는 바뀌지 않았다
    APPLIED = "applied"


class Book(TimestampMixin, Base):
    """공식 서지. ISBN이 있는 책만 두고, 기관 API로는 쓸 수 없다."""

    __tablename__ = "books"
    __table_args__ = (
        CheckConstraint(f"isbn ~ '{ISBN_PATTERN}'", name="isbn_format"),
        CheckConstraint("list_price >= 0", name="list_price_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    isbn: Mapped[str] = mapped_column(CHAR(13), unique=True)
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str] = mapped_column(String(300))
    publisher: Mapped[str | None] = mapped_column(String(200))
    published_date: Mapped[date | None] = mapped_column(Date)
    list_price: Mapped[int | None] = mapped_column(Integer)
    kdc: Mapped[str | None] = mapped_column(String(20))
    cover_url: Mapped[str | None] = mapped_column(String(1000))
    description: Mapped[str | None] = mapped_column(Text)
    subtitle: Mapped[str | None] = mapped_column(String(500))
    table_of_contents: Mapped[str | None] = mapped_column(Text)
    series_name: Mapped[str | None] = mapped_column(String(500))
    external_source: Mapped[ExternalSource | None] = mapped_column(
        str_enum(ExternalSource, "external_source")
    )
    external_url: Mapped[str | None] = mapped_column(String(1000))
    external_category: Mapped[str | None] = mapped_column(String(100))  # 외부 분류 원문


class LibraryBook(TimestampMixin, Base):
    """기관 도서: 이 도서관의 그 책. 기관 값, 어린이 구분, ISBN 없는 책이 여기 있다."""

    __tablename__ = "library_books"
    __table_args__ = (
        UniqueConstraint("library_id", "id", name="uq_library_books_library_id_id"),
        UniqueConstraint("library_id", "isbn", name="uq_library_books_library_id_isbn"),
        CheckConstraint(f"isbn ~ '{ISBN_PATTERN}'", name="isbn_format"),
        CheckConstraint("list_price >= 0", name="list_price_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    book_id: Mapped[int | None] = mapped_column(
        ForeignKey("books.id", ondelete="RESTRICT"), index=True
    )
    isbn: Mapped[str | None] = mapped_column(CHAR(13))
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str] = mapped_column(String(300))
    publisher: Mapped[str | None] = mapped_column(String(200))
    published_date: Mapped[date | None] = mapped_column(Date)
    list_price: Mapped[int | None] = mapped_column(Integer)
    kdc: Mapped[str | None] = mapped_column(String(20))
    audience: Mapped[Audience] = mapped_column(
        str_enum(Audience, "audience"), server_default=Audience.GENERAL.value
    )
    audience_source: Mapped[AudienceSource] = mapped_column(
        str_enum(AudienceSource, "audience_source"), server_default=AudienceSource.DEFAULT.value
    )
    cover_url: Mapped[str | None] = mapped_column(String(1000))
    description: Mapped[str | None] = mapped_column(Text)
    enrichment_status: Mapped[EnrichmentStatus] = mapped_column(
        str_enum(EnrichmentStatus, "enrichment_status"),
        server_default=EnrichmentStatus.PENDING.value,
    )
    enrichment_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    book: Mapped[Book | None] = relationship(lazy="joined")

    def shown(self, field: str) -> Any:
        """표시 값: 연결된 공식 서지의 값을 먼저 쓰고, 비어 있으면 기관 값을 쓴다."""
        official = getattr(self.book, field) if self.book is not None else None
        return official if official is not None else getattr(self, field)


class Holding(TimestampMixin, Base):
    __tablename__ = "holdings"
    __table_args__ = (
        UniqueConstraint(
            "library_id", "accession_number", name="uq_holdings_library_id_accession_number"
        ),
        UniqueConstraint("library_id", "id", name="uq_holdings_library_id_id"),
        ForeignKeyConstraint(
            ["library_id", "library_book_id"],
            ["library_books.library_id", "library_books.id"],
            name="fk_holdings_library_id_library_book_id_library_books",
            ondelete="RESTRICT",
        ),
        CheckConstraint("purchase_price >= 0", name="purchase_price_nonnegative"),
        CheckConstraint(
            "(acquisition_type = 'purchased' AND donor IS NULL"
            " AND (purchase_price IS NOT NULL OR source = 'imported'))"
            " OR (acquisition_type = 'donated' AND purchase_price IS NULL)"
            " OR (acquisition_type = 'unknown' AND purchase_price IS NULL AND donor IS NULL)",
            name="acquisition_fields",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    library_book_id: Mapped[int] = mapped_column(Integer, index=True)
    accession_number: Mapped[str] = mapped_column(String(50))
    call_number: Mapped[str | None] = mapped_column(String(100))
    shelf_location: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[HoldingStatus] = mapped_column(
        str_enum(HoldingStatus, "holding_status"), server_default=HoldingStatus.AVAILABLE.value
    )
    acquisition_type: Mapped[AcquisitionType] = mapped_column(
        str_enum(AcquisitionType, "acquisition_type")
    )
    purchase_price: Mapped[int | None] = mapped_column(Integer)
    donor: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[HoldingSource] = mapped_column(
        str_enum(HoldingSource, "holding_source"), server_default=HoldingSource.MANUAL.value
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    library_book: Mapped[LibraryBook] = relationship(lazy="joined")


class HoldingImport(TimestampMixin, Base):
    """장서 가져오기 기록. 인식한 열의 값만 rows에 둔다. 원본 파일은 저장하지 않는다."""

    __tablename__ = "holding_imports"
    __table_args__ = (
        UniqueConstraint("library_id", "id", name="uq_holding_imports_library_id_id"),
        ForeignKeyConstraint(
            ["library_id", "staff_user_id"],
            ["staff_users.library_id", "staff_users.id"],
            name="fk_holding_imports_library_id_staff_user_id_staff_users",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    staff_user_id: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(300))
    status: Mapped[ImportStatus] = mapped_column(
        str_enum(ImportStatus, "import_status"), server_default=ImportStatus.PREVIEW.value
    )
    column_mapping: Mapped[dict[str, Any]] = mapped_column(JSONB)
    rows: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
