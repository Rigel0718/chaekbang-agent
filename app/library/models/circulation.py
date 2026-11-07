"""회원과 대출 (기관별)."""

from datetime import date

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin
from app.models.catalog import Holding


class Member(TimestampMixin, Base):
    """개인정보는 회원번호와 이름만 둔다."""

    __tablename__ = "members"
    __table_args__ = (
        UniqueConstraint("library_id", "member_number", name="uq_members_library_id_member_number"),
        UniqueConstraint("library_id", "id", name="uq_members_library_id_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    member_number: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(100))


class Loan(TimestampMixin, Base):
    __tablename__ = "loans"
    __table_args__ = (
        # 같은 기관의 사본·회원만 가리킨다. member_id가 NULL이면(회원 삭제 후) 검사하지 않는다.
        ForeignKeyConstraint(
            ["library_id", "holding_id"],
            ["holdings.library_id", "holdings.id"],
            name="fk_loans_library_id_holding_id_holdings",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["library_id", "member_id"],
            ["members.library_id", "members.id"],
            name="fk_loans_library_id_member_id_members",
            ondelete="RESTRICT",
        ),
        CheckConstraint("due_on >= loaned_on", name="due_after_loaned"),
        CheckConstraint(
            "returned_on IS NOT NULL OR member_id IS NOT NULL", name="active_has_member"
        ),
        Index(
            "uq_loans_active_holding",
            "holding_id",
            unique=True,
            postgresql_where=text("returned_on IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    holding_id: Mapped[int] = mapped_column(Integer)
    member_id: Mapped[int | None] = mapped_column(Integer, index=True)
    loaned_on: Mapped[date] = mapped_column(Date)
    due_on: Mapped[date] = mapped_column(Date)
    returned_on: Mapped[date | None] = mapped_column(Date)

    holding: Mapped[Holding] = relationship(
        lazy="joined",
        primaryjoin="and_(Loan.library_id == Holding.library_id, Loan.holding_id == Holding.id)",
        foreign_keys="[Loan.library_id, Loan.holding_id]",
        viewonly=True,
    )
    member: Mapped["Member | None"] = relationship(
        lazy="joined",
        primaryjoin="and_(Loan.library_id == Member.library_id, Loan.member_id == Member.id)",
        foreign_keys="[Loan.library_id, Loan.member_id]",
        viewonly=True,
    )
