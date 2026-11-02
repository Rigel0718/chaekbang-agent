"""supply 컨텍스트 (C 기관 납품): 기관, 납품 도서 목록과 행, 견적서 초안."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CHAR,
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, str_enum


class InstitutionType(StrEnum):
    SCHOOL = "school"
    DAYCARE = "daycare"
    COMMUNITY_CENTER = "community_center"
    MILITARY = "military"
    OTHER = "other"


class InstitutionOrderStatus(StrEnum):
    UPLOADED = "uploaded"
    MATCHING = "matching"
    REVIEWING = "reviewing"
    QUOTED = "quoted"


class MatchStatus(StrEnum):
    UNMATCHED = "unmatched"
    AUTO_MATCHED = "auto_matched"
    NEEDS_CONFIRMATION = "needs_confirmation"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class QuoteDraftStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENT = "sent"


class Institution(TimestampMixin, Base):
    __tablename__ = "institutions"
    __table_args__ = (CheckConstraint("length(name) > 0", name="name_not_empty"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    type: Mapped[InstitutionType] = mapped_column(str_enum(InstitutionType, "institution_type"))
    contact_name: Mapped[str | None] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(String(50))
    email: Mapped[str | None] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(300))
    memo: Mapped[str | None] = mapped_column(Text)


class InstitutionOrder(TimestampMixin, Base):
    """기관에서 받은 도서 목록 한 건 (업로드 단위)."""

    __tablename__ = "institution_orders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    institution_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("institutions.id", ondelete="RESTRICT"), index=True
    )
    source_filename: Mapped[str] = mapped_column(String(300))
    status: Mapped[InstitutionOrderStatus] = mapped_column(
        str_enum(InstitutionOrderStatus, "institution_order_status"),
        default=InstitutionOrderStatus.UPLOADED,
        server_default=InstitutionOrderStatus.UPLOADED.value,
    )


class OrderItem(TimestampMixin, Base):
    """목록의 한 행. 업로드 원문(raw_*)과 매칭 결과를 따로 보관한다."""

    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity >= 1", name="quantity_positive"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("institution_orders.id", ondelete="RESTRICT"), index=True
    )
    row_no: Mapped[int] = mapped_column(Integer)
    raw_title: Mapped[str] = mapped_column(String(500))
    raw_author: Mapped[str | None] = mapped_column(String(300))
    raw_publisher: Mapped[str | None] = mapped_column(String(200))
    raw_isbn: Mapped[str | None] = mapped_column(String(50))
    raw_volume: Mapped[str | None] = mapped_column(String(50))
    quantity: Mapped[int] = mapped_column(Integer)
    matched_isbn: Mapped[str | None] = mapped_column(
        CHAR(13), ForeignKey("books.isbn", ondelete="RESTRICT")
    )
    confidence: Mapped[float | None] = mapped_column(Float)
    match_status: Mapped[MatchStatus] = mapped_column(
        str_enum(MatchStatus, "match_status"),
        default=MatchStatus.UNMATCHED,
        server_default=MatchStatus.UNMATCHED.value,
    )


class QuoteDraft(TimestampMixin, Base):
    """기관에 보낼 견적서 초안 (글귀 아님 — 글귀는 owner_ops.Quote). 금액은 원 단위 정수."""

    __tablename__ = "quote_drafts"
    __table_args__ = (
        CheckConstraint("subtotal >= 0", name="subtotal_nonnegative"),
        CheckConstraint("discount_amount >= 0", name="discount_amount_nonnegative"),
        CheckConstraint("total >= 0", name="total_nonnegative"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    institution_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("institutions.id", ondelete="RESTRICT"), index=True
    )
    order_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("institution_orders.id", ondelete="RESTRICT")
    )
    subtotal: Mapped[int] = mapped_column(Integer)
    discount_amount: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    status: Mapped[QuoteDraftStatus] = mapped_column(
        str_enum(QuoteDraftStatus, "quote_draft_status"),
        default=QuoteDraftStatus.DRAFT,
        server_default=QuoteDraftStatus.DRAFT.value,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
