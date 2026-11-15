"""add official book embeddings: official_book_embeddings, book_embeddings.kind, books.series_keys

공식 서지 벡터(기관 공통 테이블)를 새로 두고, 기관 도서 벡터에 종류 칸을 더한다. 공식 서지에는
시리즈 키를 더한다. 기존 기관 도서 벡터는 종류 `full`이 된다.

Revision ID: 2500fbca0204
Revises: 49392728f35a
Create Date: 2026-11-15 15:08:40.767351

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "2500fbca0204"
down_revision: str | Sequence[str] | None = "49392728f35a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "official_book_embeddings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("text_version", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
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
        sa.CheckConstraint("kind <> ''", name=op.f("ck_official_book_embeddings_kind_not_empty")),
        sa.ForeignKeyConstraint(
            ["book_id"],
            ["books.id"],
            name=op.f("fk_official_book_embeddings_book_id_books"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_official_book_embeddings")),
        sa.UniqueConstraint(
            "book_id",
            "model_name",
            "text_version",
            "kind",
            name="uq_official_book_embeddings_book_model_version_kind",
        ),
    )
    op.add_column(
        "book_embeddings",
        sa.Column("kind", sa.String(length=32), server_default="full", nullable=False),
    )
    op.alter_column("book_embeddings", "kind", server_default=None)
    op.create_check_constraint(
        op.f("ck_book_embeddings_kind_not_empty"), "book_embeddings", "kind <> ''"
    )
    op.drop_constraint(
        op.f("uq_book_embeddings_library_book_model_version"), "book_embeddings", type_="unique"
    )
    op.create_unique_constraint(
        "uq_book_embeddings_library_book_model_version_kind",
        "book_embeddings",
        ["library_id", "library_book_id", "model_name", "text_version", "kind"],
    )
    op.add_column(
        "books",
        sa.Column(
            "series_keys",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    # 종류가 `full`이 아닌 기관 도서 벡터가 있으면 옛 유니크 키를 만들 수 없어 먼저 지운다
    op.execute("DELETE FROM book_embeddings WHERE kind <> 'full'")
    op.drop_column("books", "series_keys")
    op.drop_constraint(
        "uq_book_embeddings_library_book_model_version_kind", "book_embeddings", type_="unique"
    )
    op.create_unique_constraint(
        op.f("uq_book_embeddings_library_book_model_version"),
        "book_embeddings",
        ["library_id", "library_book_id", "model_name", "text_version"],
        postgresql_nulls_not_distinct=False,
    )
    op.drop_constraint(op.f("ck_book_embeddings_kind_not_empty"), "book_embeddings", type_="check")
    op.drop_column("book_embeddings", "kind")
    op.drop_table("official_book_embeddings")
