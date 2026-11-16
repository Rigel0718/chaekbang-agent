"""require korean collation: 서명 정렬에 쓰는 ko-x-icu가 있는지 확인한다

스키마는 바꾸지 않는다. ICU 없이 빌드된 PostgreSQL에서는 찾기·목록이 정렬할 때 실패하므로
여기서 먼저 분명한 오류로 멈춘다.

Revision ID: 1071ac4133cf
Revises: 2500fbca0204
Create Date: 2026-11-16 10:33:00

"""

from collections.abc import Sequence

from alembic import op

from app.core.migrations import require_collation
from app.core.text import KOREAN_COLLATION

# revision identifiers, used by Alembic.
revision: str = "1071ac4133cf"
down_revision: str | Sequence[str] | None = "2500fbca0204"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    require_collation(op.get_bind(), KOREAN_COLLATION)


def downgrade() -> None:
    pass
