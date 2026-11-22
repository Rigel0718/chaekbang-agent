"""희망도서 신청 (기관별). 이용자가 도서관에 없는 책을 회원번호로 신청한다.

승인 흐름 대상이 아니다(`requested` → `closed` 두 값). 자유 글 칸은 두지 않는다. 공용 PC라
개인정보가 섞일 수 있어서다. 회원을 지우면 `member_id`만 비우고 행은 남긴다(구매 근거).
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
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.model_base import Base, TimestampMixin, str_enum
from app.library.models.circulation import Member

TITLE_LIMIT = 200
AUTHOR_LIMIT = 100


class BookRequestStatus(StrEnum):
    REQUESTED = "requested"
    CLOSED = "closed"


class BookRequest(TimestampMixin, Base):
    __tablename__ = "book_requests"
    __table_args__ = (
        # 같은 기관의 회원만 가리킨다. member_id가 NULL이면(회원 삭제 후) 검사하지 않는다.
        ForeignKeyConstraint(
            ["library_id", "member_id"],
            ["members.library_id", "members.id"],
            name="fk_book_requests_library_id_member_id_members",
            ondelete="RESTRICT",
        ),
        CheckConstraint("length(title) > 0", name="title_not_empty"),
        CheckConstraint("length(title_key) > 0", name="title_key_not_empty"),
        # 같은 회원이 같은 서명으로 처리 전 신청을 하나만 둔다(동시 요청도 막는다)
        Index(
            "uq_book_requests_open_member_title",
            "library_id",
            "member_id",
            "title_key",
            unique=True,
            postgresql_where=text("status = 'requested'"),
        ),
        Index("ix_book_requests_library_status_created", "library_id", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    member_id: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(TITLE_LIMIT))
    title_key: Mapped[str] = mapped_column(String(TITLE_LIMIT * 2))  # 서명 맞춤 키, 중복 비교용
    author: Mapped[str | None] = mapped_column(String(AUTHOR_LIMIT))
    isbn: Mapped[str | None] = mapped_column(String(13))
    status: Mapped[BookRequestStatus] = mapped_column(
        str_enum(BookRequestStatus, "book_request_status"),
        default=BookRequestStatus.REQUESTED,
        server_default=BookRequestStatus.REQUESTED.value,
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    member: Mapped[Member | None] = relationship(
        lazy="joined",
        primaryjoin="and_(BookRequest.library_id == Member.library_id, "
        "BookRequest.member_id == Member.id)",
        foreign_keys="[BookRequest.library_id, BookRequest.member_id]",
        viewonly=True,
    )

    @property
    def member_number(self) -> str | None:
        """관리자 목록에만 쓴다. 회원이 지워졌으면 None."""
        return self.member.member_number if self.member else None
