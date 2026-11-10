"""실행 기록 쓰기와 기관 범위 조회. 쓰기는 커밋까지 해서 외부 호출 동안 트랜잭션을 남기지 않는다."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.models import AgentRun, AgentStep, RunStatus, StepKind
from app.core import clock
from app.core.tenancy import get_owned

LABEL = "실행"


async def start_run(
    session: AsyncSession, library_id: int, *, profile: str, profile_version: str, model: str
) -> AgentRun:
    run = AgentRun(
        library_id=library_id,
        profile=profile,
        profile_version=profile_version,
        model=model,
        status=RunStatus.RUNNING,
        started_at=clock.now(),
    )
    session.add(run)
    await session.commit()
    return run


async def add_step(
    session: AsyncSession,
    library_id: int,
    run_id: int,
    seq: int,
    kind: StepKind,
    *,
    duration_ms: int,
    name: str | None = None,
    is_error: bool = False,
    detail: dict[str, Any] | None = None,
) -> None:
    """실행은 id로 받는다. tool 오류 뒤의 rollback이 실행 객체를 만료시켜도 읽지 않게 한다."""
    session.add(
        AgentStep(
            library_id=library_id,
            run_id=run_id,
            seq=seq,
            kind=kind,
            name=name,
            is_error=is_error,
            duration_ms=duration_ms,
            detail=detail,
        )
    )
    await session.commit()


async def finish_run(
    session: AsyncSession,
    run: AgentRun,
    status: RunStatus,
    *,
    input_tokens: int,
    cached_input_tokens: int,
    cache_write_tokens: int,
    output_tokens: int,
) -> None:
    run.status = status
    run.input_tokens = input_tokens
    run.cached_input_tokens = cached_input_tokens
    run.cache_write_tokens = cache_write_tokens
    run.output_tokens = output_tokens
    run.finished_at = clock.now()
    await session.commit()


async def get_run(session: AsyncSession, library_id: int, run_id: int) -> AgentRun:
    return await get_owned(session, AgentRun, library_id, run_id, label=LABEL)


async def list_steps(session: AsyncSession, library_id: int, run_id: int) -> list[AgentStep]:
    await get_run(session, library_id, run_id)
    rows = await session.scalars(
        select(AgentStep)
        .where(AgentStep.library_id == library_id, AgentStep.run_id == run_id)
        .order_by(AgentStep.seq)
    )
    return list(rows)
