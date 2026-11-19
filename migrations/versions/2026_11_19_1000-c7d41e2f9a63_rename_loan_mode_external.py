"""rename loan mode external

libraries.loan_mode의 값 `imported`를 `external`로 바꾼다(rename-loan-mode-external).
사본 출처(holdings.source)의 `imported`는 그대로다. 제약 이름은 명명 규칙(ck_<표>_<이름>)을 따른다.

Revision ID: c7d41e2f9a63
Revises: a43f60777b8e
Create Date: 2026-11-19 10:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7d41e2f9a63"
down_revision: str | Sequence[str] | None = "a43f60777b8e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT = "ck_libraries_loan_mode"


def _swap(old: str, new: str) -> None:
    # 제약을 먼저 지워야 새 값을 넣을 수 있다.
    op.execute(f"ALTER TABLE libraries DROP CONSTRAINT {CONSTRAINT}")
    op.execute(f"UPDATE libraries SET loan_mode = '{new}' WHERE loan_mode = '{old}'")
    op.execute(
        f"ALTER TABLE libraries ADD CONSTRAINT {CONSTRAINT}"
        f" CHECK (loan_mode IN ('{new}', 'internal'))"
    )


def upgrade() -> None:
    """Upgrade schema."""
    _swap("imported", "external")


def downgrade() -> None:
    """Downgrade schema."""
    _swap("external", "imported")
