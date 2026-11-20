"""add overdue notice

연체 안내(add-overdue-notice): 회원 전화번호(선택)와 안내문 틀. 틀의 상태 칸은 공통 승인 상태
(`approval_status`)이다. 기존 회원 행의 전화번호는 비어 있다.

Revision ID: 30ae01e7bb26
Revises: e5911a0cf521
Create Date: 2026-11-21 04:08:20.670680

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "30ae01e7bb26"
down_revision: str | Sequence[str] | None = "e5911a0cf521"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "overdue_notice_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("library_id", sa.Integer(), nullable=False),
        sa.Column("body", sa.String(length=300), nullable=False),
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
        sa.CheckConstraint(
            "length(body) > 0", name=op.f("ck_overdue_notice_templates_body_not_empty")
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["staff_users.id"],
            name=op.f("fk_overdue_notice_templates_approved_by_staff_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["staff_users.id"],
            name=op.f("fk_overdue_notice_templates_created_by_staff_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["library_id"],
            ["libraries.id"],
            name=op.f("fk_overdue_notice_templates_library_id_libraries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_overdue_notice_templates")),
        sa.UniqueConstraint("library_id", "id", name="uq_overdue_notice_templates_library_id_id"),
    )
    op.create_index(
        "ix_overdue_notice_templates_library_status_executed",
        "overdue_notice_templates",
        ["library_id", "status", "executed_at"],
        unique=False,
    )
    op.add_column("members", sa.Column("phone", sa.String(length=11), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("members", "phone")
    op.drop_index(
        "ix_overdue_notice_templates_library_status_executed", table_name="overdue_notice_templates"
    )
    op.drop_table("overdue_notice_templates")
