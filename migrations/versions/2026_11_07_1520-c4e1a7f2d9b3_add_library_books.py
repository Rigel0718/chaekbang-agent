"""add library books

공식 서지(books)와 기관 도서(library_books)를 나눈다. 기존 books의 값은 기관이 올린 값이라
공식 서지로 보지 않고 기관 도서로 옮긴 뒤 books를 비운다. 사본이 없던 도서는 사라진다.

Revision ID: c4e1a7f2d9b3
Revises: ad7ab6a0d591
Create Date: 2026-11-07 15:20:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e1a7f2d9b3"
down_revision: str | Sequence[str] | None = "ad7ab6a0d591"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BOOK_VALUES = "title, author, publisher, published_date, list_price, kdc, cover_url, description"
AUDIENCE_VALUES = "audience, audience_source"
NEW_HOLDING_FK = "fk_holdings_library_id_library_book_id_library_books"


def _enum(name: str, *values: str) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "library_books",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("library_id", sa.Integer(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=True),
        sa.Column("isbn", sa.CHAR(length=13), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("author", sa.String(length=300), nullable=False),
        sa.Column("publisher", sa.String(length=200), nullable=True),
        sa.Column("published_date", sa.Date(), nullable=True),
        sa.Column("list_price", sa.Integer(), nullable=True),
        sa.Column("kdc", sa.String(length=20), nullable=True),
        sa.Column(
            "audience",
            _enum("audience", "children", "general"),
            server_default="general",
            nullable=False,
        ),
        sa.Column(
            "audience_source",
            _enum("audience_source", "default", "manual", "import_label"),
            server_default="default",
            nullable=False,
        ),
        sa.Column("cover_url", sa.String(length=1000), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.Column("legacy_book_id", sa.Integer(), nullable=True),  # 옮기는 동안만 쓴다
        sa.CheckConstraint("isbn ~ '^[0-9]{13}$'", name=op.f("ck_library_books_isbn_format")),
        sa.CheckConstraint("list_price >= 0", name=op.f("ck_library_books_list_price_nonnegative")),
        sa.ForeignKeyConstraint(
            ["book_id"],
            ["books.id"],
            name=op.f("fk_library_books_book_id_books"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["library_id"],
            ["libraries.id"],
            name=op.f("fk_library_books_library_id_libraries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_library_books")),
        sa.UniqueConstraint("library_id", "id", name="uq_library_books_library_id_id"),
        sa.UniqueConstraint("library_id", "isbn", name="uq_library_books_library_id_isbn"),
    )
    op.create_index(op.f("ix_library_books_book_id"), "library_books", ["book_id"], unique=False)

    # 사본이 있는 (기관, 도서)마다 기관 도서를 만든다.
    op.execute(
        f"""
        INSERT INTO library_books
            (library_id, isbn, {BOOK_VALUES}, {AUDIENCE_VALUES}, legacy_book_id)
        SELECT h.library_id, b.isbn, {", ".join(f"b.{c}" for c in BOOK_VALUES.split(", "))},
               b.audience, b.audience_source, b.id
        FROM (SELECT DISTINCT library_id, book_id FROM holdings) h
        JOIN books b ON b.id = h.book_id
        """
    )

    op.add_column("holdings", sa.Column("library_book_id", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE holdings h SET library_book_id = lb.id
        FROM library_books lb
        WHERE lb.library_id = h.library_id AND lb.legacy_book_id = h.book_id
        """
    )
    op.alter_column("holdings", "library_book_id", nullable=False)
    op.create_foreign_key(
        NEW_HOLDING_FK,
        "holdings",
        "library_books",
        ["library_id", "library_book_id"],
        ["library_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        op.f("ix_holdings_library_book_id"), "holdings", ["library_book_id"], unique=False
    )
    op.drop_index(op.f("ix_holdings_book_id"), table_name="holdings")
    op.drop_constraint(op.f("fk_holdings_book_id_books"), "holdings", type_="foreignkey")
    op.drop_column("holdings", "book_id")
    op.drop_column("library_books", "legacy_book_id")

    op.execute("DELETE FROM books")
    op.alter_column("books", "isbn", existing_type=sa.CHAR(length=13), nullable=False)
    op.drop_column("books", "audience_source")
    op.drop_column("books", "audience")


def downgrade() -> None:
    """Downgrade schema.

    기관마다 달랐던 어린이 구분은 ISBN별로 하나로 합쳐진다. 어린이 구분이 있는 값을 먼저 쓴다.
    """
    op.add_column(
        "books",
        sa.Column("audience", sa.String(length=32), server_default="general", nullable=False),
    )
    op.add_column(
        "books",
        sa.Column(
            "audience_source", sa.String(length=32), server_default="default", nullable=False
        ),
    )
    op.create_check_constraint(
        op.f("ck_books_audience"), "books", "audience IN ('children', 'general')"
    )
    op.create_check_constraint(
        op.f("ck_books_audience_source"),
        "books",
        "audience_source IN ('default', 'manual', 'import_label')",
    )
    op.alter_column("books", "isbn", existing_type=sa.CHAR(length=13), nullable=True)
    op.add_column("books", sa.Column("legacy_library_book_id", sa.Integer(), nullable=True))

    op.execute(
        f"""
        INSERT INTO books (isbn, {BOOK_VALUES}, {AUDIENCE_VALUES})
        SELECT DISTINCT ON (isbn) isbn, {BOOK_VALUES}, {AUDIENCE_VALUES}
        FROM library_books
        WHERE isbn IS NOT NULL
        ORDER BY isbn, (audience = 'children') DESC, id
        ON CONFLICT (isbn) DO UPDATE
        SET audience = EXCLUDED.audience, audience_source = EXCLUDED.audience_source
        """
    )
    op.execute(
        f"""
        INSERT INTO books ({BOOK_VALUES}, {AUDIENCE_VALUES}, legacy_library_book_id)
        SELECT {BOOK_VALUES}, {AUDIENCE_VALUES}, id
        FROM library_books
        WHERE isbn IS NULL
        """
    )

    op.add_column("holdings", sa.Column("book_id", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE holdings h SET book_id = b.id
        FROM library_books lb
        JOIN books b ON b.isbn = lb.isbn OR b.legacy_library_book_id = lb.id
        WHERE h.library_book_id = lb.id
        """
    )
    op.alter_column("holdings", "book_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_holdings_book_id_books"),
        "holdings",
        "books",
        ["book_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_holdings_book_id"), "holdings", ["book_id"], unique=False)
    op.drop_index(op.f("ix_holdings_library_book_id"), table_name="holdings")
    op.drop_constraint(NEW_HOLDING_FK, "holdings", type_="foreignkey")
    op.drop_column("holdings", "library_book_id")
    op.drop_column("books", "legacy_library_book_id")
    op.drop_index(op.f("ix_library_books_book_id"), table_name="library_books")
    op.drop_table("library_books")
