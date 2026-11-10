"""add librarian chat and recommendation events

Revision ID: c4e2a7d9f1b3
Revises: b3f1c8d2e6a4
Create Date: 2026-11-10 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e2a7d9f1b3"
down_revision: str | Sequence[str] | None = "b3f1c8d2e6a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CHAT_ROLES = ("user", "assistant")


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("library_id", sa.Integer(), nullable=False),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("busy_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["library_id"],
            ["libraries.id"],
            name=op.f("fk_chat_sessions_library_id_libraries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_sessions")),
        sa.UniqueConstraint("library_id", "id", name="uq_chat_sessions_library_id_id"),
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("library_id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("role", _enum("chat_role", *CHAT_ROLES), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["library_id", "session_id"],
            ["chat_sessions.library_id", "chat_sessions.id"],
            name="fk_chat_messages_library_id_session_id_chat_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["library_id"],
            ["libraries.id"],
            name=op.f("fk_chat_messages_library_id_libraries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chat_messages")),
    )
    op.create_index(
        "ix_chat_messages_library_id_session_id",
        "chat_messages",
        ["library_id", "session_id"],
        unique=False,
    )
    op.create_table(
        "recommendation_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("library_id", sa.Integer(), nullable=False),
        sa.Column("library_book_id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("was_available", sa.Boolean(), nullable=False),
        sa.Column("shown_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["library_id", "library_book_id"],
            ["library_books.library_id", "library_books.id"],
            name="fk_recommendation_events_library_id_library_book_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["library_id", "run_id"],
            ["agent_runs.library_id", "agent_runs.id"],
            name="fk_recommendation_events_library_id_run_id_agent_runs",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["library_id"],
            ["libraries.id"],
            name=op.f("fk_recommendation_events_library_id_libraries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_recommendation_events")),
        sa.UniqueConstraint("run_id", "position", name="uq_recommendation_events_run_id_position"),
    )
    op.create_index(
        "ix_recommendation_events_library_id_library_book_id",
        "recommendation_events",
        ["library_id", "library_book_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_recommendation_events_library_id_library_book_id", table_name="recommendation_events"
    )
    op.drop_table("recommendation_events")
    op.drop_index("ix_chat_messages_library_id_session_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
