"""owner-ops 컨텍스트 (B 사장님 운영): 오늘의 추천·추천 카드와 사장님이 등록한 글귀."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, str_enum


class CurationKind(StrEnum):
    TODAY_PICK = "today_pick"
    RECOMMENDATION_CARD = "recommendation_card"


class CurationStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    PUBLISHED = "published"


class Curation(TimestampMixin, Base):
    """오늘의 추천과 추천 카드. 승인 흐름(draft → pending_approval → approved → published)."""

    __tablename__ = "curations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    kind: Mapped[CurationKind] = mapped_column(str_enum(CurationKind, "curation_kind"))
    isbn: Mapped[str | None] = mapped_column(
        CHAR(13), ForeignKey("books.isbn", ondelete="RESTRICT")
    )
    title: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[CurationStatus] = mapped_column(
        str_enum(CurationStatus, "curation_status"),
        default=CurationStatus.DRAFT,
        server_default=CurationStatus.DRAFT.value,
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Quote(TimestampMixin, Base):
    """사장님이 등록한 글귀 (견적서 아님 — 견적서는 supply.QuoteDraft). LLM이 지어내지 않는다."""

    __tablename__ = "quotes"
    __table_args__ = (CheckConstraint("length(text) > 0", name="text_not_empty"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    isbn: Mapped[str | None] = mapped_column(
        CHAR(13), ForeignKey("books.isbn", ondelete="RESTRICT")
    )
    source_note: Mapped[str | None] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
