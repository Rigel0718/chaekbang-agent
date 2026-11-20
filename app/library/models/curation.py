"""큐레이션과 포함 도서 (기관별). 상태는 공통 승인 틀(`app/library/approval.py`)을 따른다."""

from sqlalchemy import ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.model_base import Base, TimestampMixin
from app.library.approval import ApprovalMixin

TITLE_LIMIT = 40
INTRO_LIMIT = 200
REASON_LIMIT = 60
MIN_ITEMS = 3
MAX_ITEMS = 10


class Curation(ApprovalMixin, TimestampMixin, Base):
    __tablename__ = "curations"
    __table_args__ = (
        UniqueConstraint("library_id", "id", name="uq_curations_library_id_id"),
        Index("ix_curations_library_status_executed", "library_id", "status", "executed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(TITLE_LIMIT))
    intro: Mapped[str | None] = mapped_column(String(INTRO_LIMIT))
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL")
    )

    items: Mapped[list["CurationItem"]] = relationship(
        order_by="CurationItem.position",
        primaryjoin="and_(Curation.library_id == CurationItem.library_id, "
        "Curation.id == CurationItem.curation_id)",
        foreign_keys="[CurationItem.library_id, CurationItem.curation_id]",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class CurationItem(Base):
    """큐레이션의 책 한 권. 같은 기관의 큐레이션과 기관 도서만 가리킨다."""

    __tablename__ = "curation_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["library_id", "curation_id"],
            ["curations.library_id", "curations.id"],
            name="fk_curation_items_library_id_curation_id_curations",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["library_id", "library_book_id"],
            ["library_books.library_id", "library_books.id"],
            name="fk_curation_items_library_id_library_book_id_library_books",
            ondelete="CASCADE",
        ),
        UniqueConstraint("curation_id", "position", name="uq_curation_items_curation_id_position"),
        UniqueConstraint(
            "curation_id", "library_book_id", name="uq_curation_items_curation_id_library_book_id"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    curation_id: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)
    library_book_id: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(REASON_LIMIT))
