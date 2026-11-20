"""연체 안내문 틀 (기관별). 상태는 공통 승인 틀(`app/library/approval.py`)의 확정하는 종류를 따른다.

회원 값(이름, 회원번호, 전화번호)과 채운 문안은 저장하지 않는다. 틀은 자리표시가 든 문장뿐이다.
"""

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.model_base import Base, TimestampMixin
from app.library.approval import ApprovalMixin

BODY_LIMIT = 300


class OverdueNoticeTemplate(ApprovalMixin, TimestampMixin, Base):
    __tablename__ = "overdue_notice_templates"
    __table_args__ = (
        UniqueConstraint("library_id", "id", name="uq_overdue_notice_templates_library_id_id"),
        CheckConstraint("length(body) > 0", name="body_not_empty"),
        Index(
            "ix_overdue_notice_templates_library_status_executed",
            "library_id",
            "status",
            "executed_at",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    body: Mapped[str] = mapped_column(String(BODY_LIMIT))
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("staff_users.id", ondelete="SET NULL")
    )
