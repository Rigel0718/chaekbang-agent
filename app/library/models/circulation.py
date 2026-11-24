"""회원과 대출 (기관별)."""

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.model_base import Base, TimestampMixin
from app.library.models.catalog import Holding


class Member(TimestampMixin, Base):
    """개인정보는 회원번호와 이름, 선택 전화번호(연체 안내 연락·회원 로그인용)만 둔다."""

    __tablename__ = "members"
    __table_args__ = (
        UniqueConstraint("library_id", "member_number", name="uq_members_library_id_member_number"),
        UniqueConstraint("library_id", "id", name="uq_members_library_id_id"),
        # 같은 기관 안에서 번호 하나는 회원 하나다(회원 로그인). NULL은 겹치지 않는 것으로 본다.
        UniqueConstraint("library_id", "phone", name="uq_members_library_id_phone"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    member_number: Mapped[str] = mapped_column(String(50))
    name: Mapped[str] = mapped_column(String(100))
    phone: Mapped[str | None] = mapped_column(
        String(11)
    )  # 숫자만, 관리자 API와 연체 안내 목록에서만 돌려준다


class MemberSession(TimestampMixin, Base):
    """키오스크에서 휴대폰 번호로 로그인한 회원의 짧은 세션. 키오스크 세션에 묶인다.

    토큰 원문은 저장하지 않는다. 회원을 지우면 세션도 함께 지워진다.
    """

    __tablename__ = "member_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["library_id", "member_id"],
            ["members.library_id", "members.id"],
            name="fk_member_sessions_library_id_member_id_members",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    staff_session_id: Mapped[int] = mapped_column(
        ForeignKey("staff_sessions.id", ondelete="CASCADE"), index=True
    )
    member_id: Mapped[int] = mapped_column(Integer, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


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


class BasketItem(Base):
    """회원이 담은 책 한 권. 책 id와 담은 시각뿐이고 정해진 시간이 지나면 사라진다.

    같은 기관의 회원과 기관 도서만 가리키고, 회원이나 기관 도서를 지우면 함께 지워진다.
    추천·분석·기록 어디에도 쓰지 않는다(`circulation/member-basket` 스펙).
    """

    __tablename__ = "basket_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["library_id", "member_id"],
            ["members.library_id", "members.id"],
            name="fk_basket_items_library_id_member_id_members",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["library_id", "library_book_id"],
            ["library_books.library_id", "library_books.id"],
            name="fk_basket_items_library_id_library_book_id_library_books",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "library_id",
            "member_id",
            "library_book_id",
            name="uq_basket_items_library_id_member_id_library_book_id",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    member_id: Mapped[int] = mapped_column(Integer)
    library_book_id: Mapped[int] = mapped_column(Integer)
    # 담은 시각. 보관 3시간의 기준이라 DB 기본값이 아니라 코드(clock.now)가 넣는다.
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
