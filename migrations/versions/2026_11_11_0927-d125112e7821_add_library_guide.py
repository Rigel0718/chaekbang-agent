"""add library guide: contact and rules, opening hours, closures, entries

Revision ID: d125112e7821
Revises: e2b8f4a6c1d3
Create Date: 2026-11-11 09:27:21.184360

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d125112e7821"
down_revision: str | Sequence[str] | None = "e2b8f4a6c1d3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "library_closures",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("library_id", sa.Integer(), nullable=False),
        sa.Column("closed_on", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(length=100), nullable=True),
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
            ["library_id"],
            ["libraries.id"],
            name=op.f("fk_library_closures_library_id_libraries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_library_closures")),
        sa.UniqueConstraint("library_id", "closed_on", name=op.f("uq_library_closures_library_id")),
    )
    op.create_table(
        "library_guide_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("library_id", sa.Integer(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "facility",
                "rule",
                "notice",
                name="guide_entry_kind",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=50), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.ForeignKeyConstraint(
            ["library_id"],
            ["libraries.id"],
            name=op.f("fk_library_guide_entries_library_id_libraries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_library_guide_entries")),
    )
    op.create_index(
        op.f("ix_library_guide_entries_library_id"),
        "library_guide_entries",
        ["library_id"],
        unique=False,
    )
    op.create_table(
        "library_guides",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("library_id", sa.Integer(), nullable=False),
        sa.Column("contact_phone", sa.String(length=30), nullable=True),
        sa.Column("loan_limit", sa.Integer(), nullable=True),
        sa.Column(
            "closed_on_public_holidays", sa.Boolean(), server_default="false", nullable=False
        ),
        sa.Column(
            "due_on_closed_day",
            sa.Enum(
                "next_open_day",
                "keep",
                name="due_on_closed_day",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="next_open_day",
            nullable=False,
        ),
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
        sa.CheckConstraint("loan_limit >= 1", name=op.f("ck_library_guides_loan_limit_positive")),
        sa.ForeignKeyConstraint(
            ["library_id"],
            ["libraries.id"],
            name=op.f("fk_library_guides_library_id_libraries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_library_guides")),
        sa.UniqueConstraint("library_id", name=op.f("uq_library_guides_library_id")),
    )
    op.create_table(
        "library_opening_hours",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("library_id", sa.Integer(), nullable=False),
        sa.Column("weekday", sa.SmallInteger(), nullable=False),
        sa.Column("opens_at", sa.Time(), nullable=False),
        sa.Column("closes_at", sa.Time(), nullable=False),
        sa.CheckConstraint(
            "opens_at < closes_at", name=op.f("ck_library_opening_hours_opens_before_closes")
        ),
        sa.CheckConstraint(
            "weekday BETWEEN 0 AND 6", name=op.f("ck_library_opening_hours_weekday_range")
        ),
        sa.ForeignKeyConstraint(
            ["library_id"],
            ["libraries.id"],
            name=op.f("fk_library_opening_hours_library_id_libraries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_library_opening_hours")),
    )
    op.create_index(
        op.f("ix_library_opening_hours_library_id"),
        "library_opening_hours",
        ["library_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_library_opening_hours_library_id"), table_name="library_opening_hours")
    op.drop_table("library_opening_hours")
    op.drop_table("library_guides")
    op.drop_index(op.f("ix_library_guide_entries_library_id"), table_name="library_guide_entries")
    op.drop_table("library_guide_entries")
    op.drop_table("library_closures")
