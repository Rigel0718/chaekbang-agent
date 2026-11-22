"""보충 구매 요청서와 항목 (기관별). 상태는 공통 승인 틀의 확정하는 종류(`CONFIRMING`)를 따른다.

금액 칸(`total_amount`, `priced_at`, `price_source`, 항목의 `unit_price`·`amount`)은 확정할 때만
채운다. 초안과 승인 대기 동안에는 가격을 어디에도 저장하지 않는다(상세 응답에서만 계산한다).
항목은 희망도서나 기관 도서 id를 갖지 않고 ISBN으로 식별한다. 어떤 신청에서 왔는지는
`book_requests.purchase_request_id`가 답한다. 회원 값은 이 테이블들에 들어갈 길이 없다.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.model_base import Base, TimestampMixin, str_enum
from app.library.approval import ApprovalMixin

TITLE_LIMIT = 40
VENDOR_LIMIT = 50
NOTE_LIMIT = 200
ITEM_TITLE_LIMIT = 200
ITEM_AUTHOR_LIMIT = 100
REASON_LIMIT = 60
MIN_ITEMS = 1
MAX_ITEMS = 30
MIN_QUANTITY = 1
MAX_QUANTITY = 10


class ReasonKind(StrEnum):
    BOOK_REQUEST = "book_request"  # 희망도서
    POPULAR = "popular"  # 인기 대출(복본)
    FIELD_GAP = "field_gap"  # 부족 분야(관리자가 ISBN을 넣음)
    MANUAL = "manual"  # 관리자 직접


class PriceSource(StrEnum):
    YES24_LIST_PRICE = "yes24_list_price"


class PurchaseRequest(ApprovalMixin, TimestampMixin, Base):
    __tablename__ = "purchase_requests"
    __table_args__ = (
        UniqueConstraint("library_id", "id", name="uq_purchase_requests_library_id_id"),
        CheckConstraint("length(title) > 0", name="title_not_empty"),
        CheckConstraint("total_amount >= 0", name="total_amount_nonnegative"),
        Index("ix_purchase_requests_library_status_created", "library_id", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(TITLE_LIMIT))
    vendor_name: Mapped[str | None] = mapped_column(String(VENDOR_LIMIT))
    note: Mapped[str | None] = mapped_column(String(NOTE_LIMIT))
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL")
    )
    # 확정 때만 채운다(원 단위 int)
    total_amount: Mapped[int | None] = mapped_column(Integer)
    priced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    price_source: Mapped[PriceSource | None] = mapped_column(
        str_enum(PriceSource, "purchase_price_source")
    )

    items: Mapped[list["PurchaseRequestItem"]] = relationship(
        order_by="PurchaseRequestItem.position",
        primaryjoin="and_(PurchaseRequest.library_id == PurchaseRequestItem.library_id, "
        "PurchaseRequest.id == PurchaseRequestItem.purchase_request_id)",
        foreign_keys="[PurchaseRequestItem.library_id, PurchaseRequestItem.purchase_request_id]",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class PurchaseRequestItem(Base):
    """요청서의 책 한 종. 같은 기관의 요청서만 가리키고 한 요청서에 같은 ISBN은 하나다."""

    __tablename__ = "purchase_request_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["library_id", "purchase_request_id"],
            ["purchase_requests.library_id", "purchase_requests.id"],
            name="fk_purchase_request_items_library_id_request_id_requests",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "purchase_request_id", "position", name="uq_purchase_request_items_request_id_position"
        ),
        UniqueConstraint(
            "purchase_request_id", "isbn", name="uq_purchase_request_items_request_id_isbn"
        ),
        CheckConstraint(
            f"quantity BETWEEN {MIN_QUANTITY} AND {MAX_QUANTITY}", name="quantity_in_range"
        ),
        CheckConstraint("length(title) > 0", name="title_not_empty"),
        CheckConstraint("unit_price >= 0", name="unit_price_nonnegative"),
        CheckConstraint("amount >= 0", name="amount_nonnegative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    purchase_request_id: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    isbn: Mapped[str] = mapped_column(String(13))
    title: Mapped[str] = mapped_column(String(ITEM_TITLE_LIMIT))
    author: Mapped[str | None] = mapped_column(String(ITEM_AUTHOR_LIMIT))
    quantity: Mapped[int] = mapped_column(Integer)
    reason_kind: Mapped[ReasonKind] = mapped_column(str_enum(ReasonKind, "purchase_reason_kind"))
    reason: Mapped[str | None] = mapped_column(String(REASON_LIMIT))
    # 확정 때만 채운다(원 단위 int)
    unit_price: Mapped[int | None] = mapped_column(Integer)
    amount: Mapped[int | None] = mapped_column(Integer)
