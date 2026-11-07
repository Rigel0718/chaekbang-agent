"""에이전트 실행 기록. 이용자 문장, 모델이 쓴 글, tool 결과 원문은 저장하지 않는다."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.model_base import Base, str_enum


class RunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"  # 검사를 통과한 답이 나갔다
    REPAIRED = "repaired"  # 위반 항목을 뺀 답이 나갔다
    FALLBACK = "fallback"  # 고정 답이 나갔다
    REFUSED = "refused"  # LLM이 거절했다
    FAILED = "failed"  # 오류로 끝났다
    CANCELLED = "cancelled"  # 소비자가 중간에 멈췄다


class StepKind(StrEnum):
    LLM = "llm"
    TOOL = "tool"
    CHECK = "check"


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (UniqueConstraint("library_id", "id", name="uq_agent_runs_library_id_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    profile: Mapped[str] = mapped_column(String(50))
    profile_version: Mapped[str] = mapped_column(String(50))
    model: Mapped[str] = mapped_column(String(100))
    status: Mapped[RunStatus] = mapped_column(
        str_enum(RunStatus, "run_status"), server_default=RunStatus.RUNNING.value
    )
    input_tokens: Mapped[int] = mapped_column(Integer, server_default="0")  # 캐시 입력 포함
    cached_input_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    cache_write_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, server_default="0")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AgentStep(Base):
    __tablename__ = "agent_steps"
    __table_args__ = (
        ForeignKeyConstraint(
            ["library_id", "run_id"],
            ["agent_runs.library_id", "agent_runs.id"],
            name="fk_agent_steps_library_id_run_id_agent_runs",
            ondelete="RESTRICT",
        ),
    )

    library_id: Mapped[int] = mapped_column(
        ForeignKey("libraries.id", ondelete="RESTRICT"), primary_key=True
    )
    run_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[StepKind] = mapped_column(str_enum(StepKind, "step_kind"))
    name: Mapped[str | None] = mapped_column(String(100))  # tool 또는 검사 이름
    is_error: Mapped[bool] = mapped_column(server_default="false")
    duration_ms: Mapped[int] = mapped_column(Integer)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB)  # 고른 입력 값, 위반 항목
