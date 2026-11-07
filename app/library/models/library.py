"""기관과 직원 계정, 로그인 세션."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.model_base import Base, TimestampMixin, str_enum


class LibraryType(StrEnum):
    SMALL_LIBRARY = "small_library"
    BOOKSTORE = "bookstore"


class LoanMode(StrEnum):
    IMPORTED = "imported"  # 기존 대출 프로그램에서 가져오기
    INTERNAL = "internal"  # AI 사서가 대출까지 처리


class StaffRole(StrEnum):
    ADMIN = "admin"
    KIOSK = "kiosk"


class Library(TimestampMixin, Base):
    __tablename__ = "libraries"
    __table_args__ = (CheckConstraint("default_loan_days >= 1", name="default_loan_days_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    type: Mapped[LibraryType] = mapped_column(str_enum(LibraryType, "library_type"))
    loan_mode: Mapped[LoanMode] = mapped_column(str_enum(LoanMode, "loan_mode"))
    default_loan_days: Mapped[int] = mapped_column(Integer, server_default="14")


class StaffUser(TimestampMixin, Base):
    __tablename__ = "staff_users"
    __table_args__ = (UniqueConstraint("library_id", "id", name="uq_staff_users_library_id_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    login_id: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[StaffRole] = mapped_column(str_enum(StaffRole, "staff_role"))
    is_active: Mapped[bool] = mapped_column(server_default="true")


class StaffSession(TimestampMixin, Base):
    __tablename__ = "staff_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["library_id", "staff_user_id"],
            ["staff_users.library_id", "staff_users.id"],
            name="fk_staff_sessions_library_id_staff_user_id_staff_users",
            ondelete="RESTRICT",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    staff_user_id: Mapped[int] = mapped_column(Integer, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
