"""AI 사서 대화와 추천 노출 기록 (기관별).

대화는 진행 중에만 두고 세션이 끝나면 지운다. 메시지에는 가린 이용자 문장과 최종 답만 둔다.
노출 기록은 세션과 잇지 않아서 세션을 지워도 남는다. 회원, 문장, 이유, 어린이 값은 두지 않는다.
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.model_base import Base, str_enum


class ChatRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatSession(Base):
    __tablename__ = "chat_sessions"
    __table_args__ = (UniqueConstraint("library_id", "id", name="uq_chat_sessions_library_id_id"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    busy_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 처리 중 표시
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        ForeignKeyConstraint(
            ["library_id", "session_id"],
            ["chat_sessions.library_id", "chat_sessions.id"],
            name="fk_chat_messages_library_id_session_id_chat_sessions",
            ondelete="CASCADE",
        ),
        Index("ix_chat_messages_library_id_session_id", "library_id", "session_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    session_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    role: Mapped[ChatRole] = mapped_column(str_enum(ChatRole, "chat_role"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RecommendationEvent(Base):
    __tablename__ = "recommendation_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["library_id", "library_book_id"],
            ["library_books.library_id", "library_books.id"],
            name="fk_recommendation_events_library_id_library_book_id",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["library_id", "run_id"],
            ["agent_runs.library_id", "agent_runs.id"],
            name="fk_recommendation_events_library_id_run_id_agent_runs",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("run_id", "position", name="uq_recommendation_events_run_id_position"),
        Index(
            "ix_recommendation_events_library_id_library_book_id", "library_id", "library_book_id"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    library_book_id: Mapped[int] = mapped_column(Integer)
    run_id: Mapped[int] = mapped_column(Integer)
    position: Mapped[int] = mapped_column(Integer)  # 1부터
    was_available: Mapped[bool]  # 노출 시점에 대출 가능한 사본이 있었는지
    shown_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
