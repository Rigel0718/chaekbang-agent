"""확정 작업의 공통 승인 틀: 상태 값, 전이 표, 조건부 갱신 전이, 승인 칸.

큐레이션 게시, 연체 안내, 구매 요청서 확정이 같은 상태와 전이 규칙을 쓴다. 상태는 종류별 테이블의
`status` 칸에만 둔다(공통 승인 표 없음). 승인 뒤 실행(게시·확정)은 에이전트가 아니라 승인
요청을 받은 코드가 같은 트랜잭션에서 한다. 상태가 DB에만 있으므로
서버가 다시 시작돼도 승인이 이어진다.

새 종류를 더하려면 테이블에 `ApprovalMixin`을 섞고, 그 종류의 `TransitionTable`을 만들어 service에서
`transition()`을 부른다. 내용 수정·삭제 전에는 `require_status(row, ApprovalStatus.DRAFT)`를 부른다.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, declared_attr, mapped_column

from app.core.errors import ConflictError, NotFoundError
from app.core.model_base import str_enum

REASON_LIMIT = 200


class ApprovalStatus(StrEnum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    PUBLISHED = "published"  # 게시하는 종류(큐레이션)의 실행 상태
    CONFIRMED = "confirmed"  # 확정하는 종류(연체 안내, 구매 요청서)의 실행 상태
    ARCHIVED = "archived"  # 게시본을 내림


class Action(StrEnum):
    SUBMIT = "submit"
    APPROVE = "approve"
    REJECT = "reject"
    UNPUBLISH = "unpublish"


STATUS_LABELS = {
    ApprovalStatus.DRAFT: "초안",
    ApprovalStatus.PENDING_APPROVAL: "승인 대기",
    ApprovalStatus.APPROVED: "승인",
    ApprovalStatus.PUBLISHED: "게시",
    ApprovalStatus.CONFIRMED: "확정",
    ApprovalStatus.ARCHIVED: "내림",
}


@dataclass(frozen=True)
class TransitionTable:
    """종류마다의 전이. 승인은 `pending_approval → approved`이고, 실행 상태(`executed`)는 승인한
    코드가 실행을 마친 뒤 `mark_executed`로 둔다. 내리기가 없는 종류는 `archivable=False`다."""

    executed: ApprovalStatus
    archivable: bool

    def edges(self) -> dict[Action, tuple[ApprovalStatus, ApprovalStatus]]:
        edges = {
            Action.SUBMIT: (ApprovalStatus.DRAFT, ApprovalStatus.PENDING_APPROVAL),
            Action.APPROVE: (ApprovalStatus.PENDING_APPROVAL, ApprovalStatus.APPROVED),
            Action.REJECT: (ApprovalStatus.PENDING_APPROVAL, ApprovalStatus.DRAFT),
        }
        if self.archivable:
            edges[Action.UNPUBLISH] = (self.executed, ApprovalStatus.ARCHIVED)
        return edges


PUBLISHING = TransitionTable(executed=ApprovalStatus.PUBLISHED, archivable=True)
CONFIRMING = TransitionTable(executed=ApprovalStatus.CONFIRMED, archivable=False)


class ApprovalMixin:
    """승인 칸. 종류별 테이블이 같은 이름으로 가진다."""

    @declared_attr
    def status(cls) -> Mapped[ApprovalStatus]:
        return mapped_column(
            str_enum(ApprovalStatus, "approval_status"),
            server_default=ApprovalStatus.DRAFT.value,
        )

    @declared_attr
    def approved_by(cls) -> Mapped[int | None]:
        return mapped_column(ForeignKey("staff_users.id", ondelete="SET NULL"))

    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rejected_reason: Mapped[str | None] = mapped_column(String(REASON_LIMIT))


_ACTION_LABELS = {
    Action.SUBMIT: "제출",
    Action.APPROVE: "승인",
    Action.REJECT: "반려",
    Action.UNPUBLISH: "내리기",
}


def _conflict(label: str, status: ApprovalStatus, action: Action) -> ConflictError:
    return ConflictError(
        f"{label}이(가) {STATUS_LABELS[status]} 상태라 {_ACTION_LABELS[action]}할 수 없습니다"
    )


def require_status(row: Any, status: ApprovalStatus, *, label: str, doing: str) -> None:
    """내용 수정·삭제 같은 상태 조건 확인. 맞지 않으면 409."""
    if row.status != status:
        raise ConflictError(
            f"{label}이(가) {STATUS_LABELS[row.status]} 상태라 {doing}할 수 없습니다"
        )


async def transition(
    session: AsyncSession,
    model: type,
    table: TransitionTable,
    library_id: int,
    id: int,
    action: Action,
    *,
    label: str,
    values: dict[str, Any] | None = None,
) -> None:
    """조건부 갱신으로 상태를 바꾼다. 다른 기관이거나 없으면 404, 상태가 맞지 않으면 409.

    `WHERE status = :from`이라 같은 초안에 겹친 요청은 하나만 반영된다. 커밋은 부르는 쪽이 한다.
    """
    edges = table.edges()
    if action not in edges:
        raise ConflictError(f"{label}은(는) {_ACTION_LABELS[action]}할 수 없습니다")
    source, target = edges[action]
    result = await session.execute(
        update(model)
        .where(model.id == id, model.library_id == library_id, model.status == source)
        .values(status=target, **(values or {}))
        .returning(model.id)
        .execution_options(synchronize_session=False)
    )
    if result.scalar_one_or_none() is not None:
        return
    current = await session.scalar(
        select(model.status).where(model.id == id, model.library_id == library_id)
    )
    if current is None:
        raise NotFoundError(f"{label}을(를) 찾을 수 없습니다: {id}")
    raise _conflict(label, ApprovalStatus(current), action)


async def mark_executed(
    session: AsyncSession,
    model: type,
    table: TransitionTable,
    library_id: int,
    id: int,
    executed_at: datetime,
) -> None:
    """승인한 같은 트랜잭션에서 실행을 마친 뒤 실행 상태로 둔다."""
    await session.execute(
        update(model)
        .where(
            model.id == id,
            model.library_id == library_id,
            model.status == ApprovalStatus.APPROVED,
        )
        .values(status=table.executed, executed_at=executed_at)
        .execution_options(synchronize_session=False)
    )
