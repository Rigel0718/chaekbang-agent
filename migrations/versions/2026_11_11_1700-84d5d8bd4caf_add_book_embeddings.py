"""add book embeddings: vector extension, book_embeddings

Revision ID: 84d5d8bd4caf
Revises: d125112e7821
Create Date: 2026-11-11 17:00:39.988607

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "84d5d8bd4caf"
down_revision: str | Sequence[str] | None = "d125112e7821"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "book_embeddings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("library_id", sa.Integer(), nullable=False),
        sa.Column("library_book_id", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("text_version", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column("content_hash", sa.CHAR(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["library_id", "library_book_id"],
            ["library_books.library_id", "library_books.id"],
            name="fk_book_embeddings_library_id_library_book_id_library_books",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["library_id"],
            ["libraries.id"],
            name=op.f("fk_book_embeddings_library_id_libraries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_book_embeddings")),
        sa.UniqueConstraint(
            "library_id",
            "library_book_id",
            "model_name",
            "text_version",
            name="uq_book_embeddings_library_book_model_version",
        ),
    )


def downgrade() -> None:
    op.drop_table("book_embeddings")
    op.execute("DROP EXTENSION IF EXISTS vector")
