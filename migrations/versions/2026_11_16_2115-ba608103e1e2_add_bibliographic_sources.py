"""add bibliographic sources: 공식 서지에 KDC 분류명, 부가기호, 권, 필드별 출처를 더한다

출처 값도 넓힌다(정보나루, 카카오). 출처 값은 CHECK 제약이다(native ENUM이 아니다).
되돌리기는 새 출처 값을 쓰는 행이 있으면 제약을 다시 걸 수 없어 실패한다.
그 행을 먼저 지우거나 백업으로 되돌린다.

Revision ID: ba608103e1e2
Revises: 1071ac4133cf
Create Date: 2026-11-16 21:15:22.212060

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "ba608103e1e2"
down_revision: str | Sequence[str] | None = "1071ac4133cf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("books", sa.Column("kdc_name", sa.String(length=200), nullable=True))
    op.add_column("books", sa.Column("addition_symbol", sa.CHAR(length=5), nullable=True))
    op.add_column("books", sa.Column("volume", sa.String(length=50), nullable=True))
    op.add_column(
        "books",
        sa.Column(
            "field_sources",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        op.f("ck_books_addition_symbol_format"), "books", "addition_symbol ~ '^[0-9]{5}$'"
    )
    op.drop_constraint(op.f("ck_books_external_source"), "books", type_="check")
    op.create_check_constraint(
        op.f("ck_books_external_source"),
        "books",
        "external_source IN ('yes24', 'data4library', 'kakao')",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_books_external_source"), "books", type_="check")
    op.create_check_constraint(
        op.f("ck_books_external_source"), "books", "external_source IN ('yes24')"
    )
    op.drop_constraint(op.f("ck_books_addition_symbol_format"), "books", type_="check")
    op.drop_column("books", "field_sources")
    op.drop_column("books", "volume")
    op.drop_column("books", "addition_symbol")
    op.drop_column("books", "kdc_name")
