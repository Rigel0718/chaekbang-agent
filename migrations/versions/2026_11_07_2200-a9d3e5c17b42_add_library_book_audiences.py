"""add library book audiences

어린이 구분을 기관 도서에서 어린이 기능의 테이블로 옮긴다. default 근거는 행을 만들지 않는다.

Revision ID: a9d3e5c17b42
Revises: e7b2c91f4a06
Create Date: 2026-11-07 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a9d3e5c17b42"
down_revision: str | Sequence[str] | None = "e7b2c91f4a06"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

AUDIENCES = ("children", "general")
SOURCES = ("default", "manual", "import_label", "external_category")


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "library_book_audiences",
        sa.Column("library_id", sa.Integer(), nullable=False),
        sa.Column("library_book_id", sa.Integer(), nullable=False),
        sa.Column("audience", _enum("audience", *AUDIENCES), nullable=False),
        sa.Column("audience_source", _enum("audience_source", *SOURCES), nullable=False),
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
        sa.CheckConstraint(
            "audience_source <> 'default'",
            name=op.f("ck_library_book_audiences_source_not_default"),
        ),
        sa.ForeignKeyConstraint(
            ["library_id", "library_book_id"],
            ["library_books.library_id", "library_books.id"],
            name="fk_library_book_audiences_library_id_library_book_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["library_id"],
            ["libraries.id"],
            name=op.f("fk_library_book_audiences_library_id_libraries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "library_id", "library_book_id", name=op.f("pk_library_book_audiences")
        ),
    )
    op.execute(
        """
        INSERT INTO library_book_audiences (library_id, library_book_id, audience, audience_source)
        SELECT library_id, id, audience, audience_source
        FROM library_books
        WHERE audience_source <> 'default'
        """
    )
    op.drop_column("library_books", "audience_source")
    op.drop_column("library_books", "audience")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "library_books",
        sa.Column("audience", sa.String(length=32), server_default="general", nullable=False),
    )
    op.add_column(
        "library_books",
        sa.Column(
            "audience_source", sa.String(length=32), server_default="default", nullable=False
        ),
    )
    op.create_check_constraint(
        op.f("ck_library_books_audience"), "library_books", "audience IN ('children', 'general')"
    )
    op.create_check_constraint(
        op.f("ck_library_books_audience_source"),
        "library_books",
        "audience_source IN ('default', 'manual', 'import_label', 'external_category')",
    )
    op.execute(
        """
        UPDATE library_books lb
        SET audience = a.audience, audience_source = a.audience_source
        FROM library_book_audiences a
        WHERE a.library_id = lb.library_id AND a.library_book_id = lb.id
        """
    )
    op.drop_table("library_book_audiences")
