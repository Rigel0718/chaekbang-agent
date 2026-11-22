"""add book requests

희망도서 신청(add-librarian-actions): 회원 연결은 대출과 같은 복합 외래 키다.
회원을 지우면 서비스가 연결만 비운다.

Revision ID: d277df838863
Revises: 30ae01e7bb26
Create Date: 2026-11-22 11:09:05.305180

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d277df838863"
down_revision: str | Sequence[str] | None = "30ae01e7bb26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "book_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("library_id", sa.Integer(), nullable=False),
        sa.Column("member_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("title_key", sa.String(length=400), nullable=False),
        sa.Column("author", sa.String(length=100), nullable=True),
        sa.Column("isbn", sa.String(length=13), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "requested",
                "closed",
                name="book_request_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            server_default="requested",
            nullable=False,
        ),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("length(title) > 0", name=op.f("ck_book_requests_title_not_empty")),
        sa.CheckConstraint(
            "length(title_key) > 0", name=op.f("ck_book_requests_title_key_not_empty")
        ),
        sa.ForeignKeyConstraint(
            ["library_id", "member_id"],
            ["members.library_id", "members.id"],
            name="fk_book_requests_library_id_member_id_members",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["library_id"],
            ["libraries.id"],
            name=op.f("fk_book_requests_library_id_libraries"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_book_requests")),
    )
    op.create_index(
        "ix_book_requests_library_status_created",
        "book_requests",
        ["library_id", "status", "created_at"],
        unique=False,
    )
    op.create_index(
        "uq_book_requests_open_member_title",
        "book_requests",
        ["library_id", "member_id", "title_key"],
        unique=True,
        postgresql_where=sa.text("status = 'requested'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_book_requests_open_member_title",
        table_name="book_requests",
        postgresql_where=sa.text("status = 'requested'"),
    )
    op.drop_index("ix_book_requests_library_status_created", table_name="book_requests")
    op.drop_table("book_requests")
