"""add book enrichment

공식 서지에 YES24 값을 담을 열을, 기관 도서에 처리 상태를 추가한다. 어린이 판단은 공식 서지에
두지 않고 기관 도서의 근거(external_category)로만 저장한다.

Revision ID: e7b2c91f4a06
Revises: c4e1a7f2d9b3
Create Date: 2026-11-07 20:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7b2c91f4a06"
down_revision: str | Sequence[str] | None = "c4e1a7f2d9b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_audience_source(*values: str) -> None:
    name = op.f("ck_library_books_audience_source")
    op.drop_constraint(name, "library_books", type_="check")
    allowed = ", ".join(repr(v) for v in values)
    op.create_check_constraint(name, "library_books", f"audience_source IN ({allowed})")


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("books", sa.Column("subtitle", sa.String(length=500), nullable=True))
    op.add_column("books", sa.Column("table_of_contents", sa.Text(), nullable=True))
    op.add_column("books", sa.Column("series_name", sa.String(length=500), nullable=True))
    op.add_column("books", sa.Column("external_source", sa.String(length=32), nullable=True))
    op.add_column("books", sa.Column("external_url", sa.String(length=1000), nullable=True))
    op.add_column("books", sa.Column("external_category", sa.String(length=100), nullable=True))
    op.create_check_constraint(
        op.f("ck_books_external_source"), "books", "external_source IN ('yes24')"
    )

    op.add_column(
        "library_books",
        sa.Column(
            "enrichment_status", sa.String(length=32), server_default="pending", nullable=False
        ),
    )
    op.add_column(
        "library_books",
        sa.Column("enrichment_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_check_constraint(
        op.f("ck_library_books_enrichment_status"),
        "library_books",
        "enrichment_status IN ('pending', 'enriched', 'not_found', 'mismatch')",
    )
    op.execute("UPDATE library_books SET enrichment_status = 'enriched' WHERE book_id IS NOT NULL")
    _replace_audience_source("default", "manual", "import_label", "external_category")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "UPDATE library_books SET audience = 'general', audience_source = 'default'"
        " WHERE audience_source = 'external_category'"
    )
    _replace_audience_source("default", "manual", "import_label")
    op.drop_constraint(op.f("ck_library_books_enrichment_status"), "library_books", type_="check")
    op.drop_column("library_books", "enrichment_checked_at")
    op.drop_column("library_books", "enrichment_status")
    op.drop_constraint(op.f("ck_books_external_source"), "books", type_="check")
    for column in (
        "external_category",
        "external_url",
        "external_source",
        "series_name",
        "table_of_contents",
        "subtitle",
    ):
        op.drop_column("books", column)
