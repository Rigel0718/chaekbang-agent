"""add chat message book ids

chat_messages에 코드가 쓰는 기관 도서 id 목록 칸을 더한다(add-related-books). 기존 행은 빈 목록이다.

Revision ID: a43f60777b8e
Revises: ba608103e1e2
Create Date: 2026-11-17 15:45:39.771929

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a43f60777b8e"
down_revision: str | Sequence[str] | None = "ba608103e1e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "chat_messages",
        sa.Column(
            "library_book_ids",
            postgresql.ARRAY(sa.Integer()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("chat_messages", "library_book_ids")
