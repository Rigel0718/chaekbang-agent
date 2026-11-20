"""add approval flow

승인 흐름(add-approval-flow): 큐레이션과 포함 도서. 상태 칸 `status`는 공통 승인 상태
(`approval_status`, VARCHAR + CHECK)이고, 포함 도서는 같은 기관의 큐레이션·기관 도서만 가리킨다.
기존 행은 바꾸지 않는다.

Revision ID: e5911a0cf521
Revises: 5e2b8c1d7f40
Create Date: 2026-11-21 02:04:49.637526

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5911a0cf521"
down_revision: str | Sequence[str] | None = "5e2b8c1d7f40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "curations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("library_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=40), nullable=False),
        sa.Column("intro", sa.String(length=200), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_reason", sa.String(length=200), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "draft",
                "pending_approval",
                "approved",
                "published",
                "confirmed",
                "archived",
                name="approval_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("approved_by", sa.Integer(), nullable=True),
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
            ["approved_by"],
            ["staff_users.id"],
            name=op.f("fk_curations_approved_by_staff_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["staff_users.id"],
            name=op.f("fk_curations_created_by_staff_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["library_id"],
            ["libraries.id"],
            name=op.f("fk_curations_library_id_libraries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_curations")),
        sa.UniqueConstraint("library_id", "id", name="uq_curations_library_id_id"),
    )
    op.create_index(
        "ix_curations_library_status_executed",
        "curations",
        ["library_id", "status", "executed_at"],
        unique=False,
    )
    op.create_table(
        "curation_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("library_id", sa.Integer(), nullable=False),
        sa.Column("curation_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("library_book_id", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=60), nullable=False),
        sa.ForeignKeyConstraint(
            ["library_id", "curation_id"],
            ["curations.library_id", "curations.id"],
            name="fk_curation_items_library_id_curation_id_curations",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["library_id", "library_book_id"],
            ["library_books.library_id", "library_books.id"],
            name="fk_curation_items_library_id_library_book_id_library_books",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["library_id"],
            ["libraries.id"],
            name=op.f("fk_curation_items_library_id_libraries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_curation_items")),
        sa.UniqueConstraint(
            "curation_id", "library_book_id", name="uq_curation_items_curation_id_library_book_id"
        ),
        sa.UniqueConstraint(
            "curation_id", "position", name="uq_curation_items_curation_id_position"
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("curation_items")
    op.drop_index("ix_curations_library_status_executed", table_name="curations")
    op.drop_table("curations")
