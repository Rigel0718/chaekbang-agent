"""도서(기관 공통 서지정보)와 소장 사본(기관별)."""

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


class Audience(StrEnum):
    CHILDREN = "children"
    GENERAL = "general"


class AudienceSource(StrEnum):
    DEFAULT = "default"  # 근거 없음
    MANUAL = "manual"  # 관리자 지정
    IMPORT_LABEL = "import_label"  # 가져온 파일의 별치기호·자료실·부가기호


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
    __tablename__ = "books"
    __table_args__ = (
        CheckConstraint(f"isbn ~ '{ISBN_PATTERN}'", name="isbn_format"),
        CheckConstraint("list_price >= 0", name="list_price_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    isbn: Mapped[str | None] = mapped_column(CHAR(13), unique=True)
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


class Holding(TimestampMixin, Base):
    __tablename__ = "holdings"
    __table_args__ = (
        UniqueConstraint(
            "library_id", "accession_number", name="uq_holdings_library_id_accession_number"
        ),
        UniqueConstraint("library_id", "id", name="uq_holdings_library_id_id"),
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
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="RESTRICT"), index=True)
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

    book: Mapped[Book] = relationship(lazy="joined")


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
