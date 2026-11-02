"""storefront 컨텍스트 (A 매장 큐레이터): 손님 대화, 사장님께 넘긴 문의, 주문 요청."""

from enum import StrEnum

from sqlalchemy import CHAR, BigInteger, CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, str_enum


class ChatRole(StrEnum):
    CUSTOMER = "customer"
    ASSISTANT = "assistant"


class OwnerMessageStatus(StrEnum):
    UNREAD = "unread"
    READ = "read"
    RESOLVED = "resolved"


class BookRequestStatus(StrEnum):
    RECEIVED = "received"
    ORDERED = "ordered"
    NOTIFIED = "notified"
    CLOSED = "closed"


class ChatLog(TimestampMixin, Base):
    __tablename__ = "chat_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[ChatRole] = mapped_column(str_enum(ChatRole, "chat_role"))
    content: Mapped[str] = mapped_column(Text)


class OwnerMessage(TimestampMixin, Base):
    """에이전트가 답하기 어려워 사장님께 넘긴 문의."""

    __tablename__ = "owner_messages"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # chat_logs.session_id 값. 세션 테이블이 없어 외래 키는 두지 않는다.
    chat_session_id: Mapped[str | None] = mapped_column(String(64))
    content: Mapped[str] = mapped_column(Text)
    contact: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[OwnerMessageStatus] = mapped_column(
        str_enum(OwnerMessageStatus, "owner_message_status"),
        default=OwnerMessageStatus.UNREAD,
        server_default=OwnerMessageStatus.UNREAD.value,
    )


class BookRequest(TimestampMixin, Base):
    """매장에 없는 책의 손님 주문 요청."""

    __tablename__ = "book_requests"
    __table_args__ = (CheckConstraint("length(contact) > 0", name="contact_not_empty"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    isbn: Mapped[str | None] = mapped_column(
        CHAR(13), ForeignKey("books.isbn", ondelete="RESTRICT")
    )
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str | None] = mapped_column(String(300))
    contact: Mapped[str] = mapped_column(String(100))
    status: Mapped[BookRequestStatus] = mapped_column(
        str_enum(BookRequestStatus, "book_request_status"),
        default=BookRequestStatus.RECEIVED,
        server_default=BookRequestStatus.RECEIVED.value,
    )
    memo: Mapped[str | None] = mapped_column(Text)
