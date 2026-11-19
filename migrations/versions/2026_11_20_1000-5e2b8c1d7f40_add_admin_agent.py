"""add admin agent

운영 에이전트(add-admin-agent): 대화 세션에 종류(`librarian`·`admin`)를 더하고, 실행 행에 최종 답의
기록 필드(`answer_record`)를 더한다. 기존 세션은 AI 사서 세션이다.

Revision ID: 5e2b8c1d7f40
Revises: c7d41e2f9a63
Create Date: 2026-11-20 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "5e2b8c1d7f40"
down_revision: str | Sequence[str] | None = "c7d41e2f9a63"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "chat_sessions",
        sa.Column(
            "kind",
            sa.Enum(
                "librarian",
                "admin",
                name="session_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="librarian",
            nullable=False,
        ),
    )
    op.add_column(
        "agent_runs",
        sa.Column("answer_record", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("agent_runs", "answer_record")
    op.drop_column("chat_sessions", "kind")
