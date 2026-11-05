"""도서(기관 공통 서지정보)와 소장 사본(기관별)."""

from datetime import date, datetime
from enum import StrEnum

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import ISBN_PATTERN, Base, TimestampMixin, str_enum


class Audience(StrEnum):
    CHILDREN = "children"
    GENERAL = "general"


class AudienceSource(StrEnum):
    DEFAULT = "default"  # 근거 없음
    MANUAL = "manual"  # 관리자 지정


class HoldingStatus(StrEnum):
    AVAILABLE = "available"
    ON_LOAN = "on_loan"
    LOST = "lost"
    DAMAGED = "damaged"


class AcquisitionType(StrEnum):
    PURCHASED = "purchased"  # 매입·공식 납품
    DONATED = "donated"  # 기증


class HoldingSource(StrEnum):
    MANUAL = "manual"
    IMPORTED = "imported"


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
            "(acquisition_type = 'purchased' AND purchase_price IS NOT NULL AND donor IS NULL)"
            " OR (acquisition_type = 'donated' AND purchase_price IS NULL)",
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
