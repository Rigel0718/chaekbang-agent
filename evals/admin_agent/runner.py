"""시나리오를 운영 에이전트 대화 service로 돌린다. 서비스와 같은 경로(`prepare_admin_turn` →
`stream_admin_turn`)를 거쳐 가리기, 프로필, 기록이 실제와 같게 돈다. 시나리오마다 새 세션이다.

tool 결과는 실행 기록에 없다. 그래서 프로필의 tool을 결과를 받아 두는 tool로 감싸 돌리고, 단계
기록(입력은 tool이 고른 값만)과 순서대로 짝짓는다. 소장 도서 검색처럼 입력을 남기지 않는 tool도
결과가 남는다. 감싼 tool은 이름, 입력, 실행 함수의 결과가 서비스와 같다. 안내문 틀 초안 tool은
입력(틀 문장)도 남기지 않으므로, 결과의 `template_id`로 저장된 틀 문장을 읽어 채점에 넘긴다.
"""

from dataclasses import replace
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import LlmClient
from app.agent.models import AgentRun, AgentStep, StepKind
from app.agent.profile import Profile
from app.agent.tools import Tool, ToolContext, ToolInput
from app.library.admin_agent import PROFILE_NAME
from app.library.models.library import LoanMode
from app.library.models.overdue_notice import OverdueNoticeTemplate
from app.library.services import admin_chat
from evals.admin_agent.fixture import EvalLibraries
from evals.admin_agent.scenarios import Scenario
from evals.admin_agent.score import ToolCallRecord, TurnRecord


def capturing(profile: Profile, sink: list[Any]) -> Profile:
    """tool마다 성공한 결과를 sink에 순서대로 받아 두는 프로필."""

    def wrap(tool: Tool) -> Tool:
        async def handler(ctx: ToolContext, data: ToolInput) -> Any:
            result = await tool.handler(ctx, data)
            sink.append(result)
            return result

        return replace(tool, handler=handler)

    return replace(profile, tools=tuple(wrap(t) for t in profile.tools))


async def _calls(
    session: AsyncSession, library_id: int, run_id: int, results: list[Any]
) -> tuple[list[ToolCallRecord], int, int]:
    steps = list(
        await session.scalars(
            select(AgentStep)
            .where(
                AgentStep.library_id == library_id,
                AgentStep.run_id == run_id,
                AgentStep.kind == StepKind.TOOL,
            )
            .order_by(AgentStep.seq)
        )
    )
    pending = iter(results)
    calls = [
        ToolCallRecord(
            step.name or "",
            step.detail or {},
            step.is_error,
            None if step.is_error else next(pending, None),
        )
        for step in steps
    ]
    tokens = (
        await session.execute(
            select(AgentRun.input_tokens, AgentRun.output_tokens)
            .where(AgentRun.library_id == library_id, AgentRun.id == run_id)
            .execution_options(populate_existing=True)
        )
    ).one()
    return calls, tokens[0], tokens[1]


async def _templates(
    session: AsyncSession, library_id: int, calls: list[ToolCallRecord]
) -> list[str]:
    ids = [
        c.result["template_id"]
        for c in calls
        if c.name == "draft_overdue_notice" and isinstance(c.result, dict)
    ]
    if not ids:
        return []
    rows = await session.scalars(
        select(OverdueNoticeTemplate.body).where(
            OverdueNoticeTemplate.library_id == library_id, OverdueNoticeTemplate.id.in_(ids)
        )
    )
    return list(rows)


def library_of(libraries: EvalLibraries, scenario: Scenario) -> int:
    internal = scenario.loan_mode == LoanMode.INTERNAL
    if scenario.curation:
        return libraries.curation_internal_id if internal else libraries.curation_external_id
    return libraries.internal_id if internal else libraries.external_id


async def run_scenario(
    session: AsyncSession,
    llm: LlmClient,
    profiles: dict[LoanMode, Profile],
    libraries: EvalLibraries,
    scenario: Scenario,
) -> TurnRecord:
    library_id = library_of(libraries, scenario)
    results: list[Any] = []
    profile = capturing(profiles[scenario.loan_mode], results)
    prepared = await admin_chat.prepare_admin_turn(
        session, library_id, None, scenario.question, profile_name=PROFILE_NAME
    )
    events = {
        e.name: e.data async for e in admin_chat.stream_admin_turn(session, llm, profile, prepared)
    }
    answer, done = events["answer"], events["done"]
    calls, input_tokens, output_tokens = await _calls(session, library_id, done["run_id"], results)
    templates = await _templates(session, library_id, calls)
    return TurnRecord(
        question=scenario.question,
        message=answer["message"],
        unsupported=answer["unsupported"],
        status=done["status"],
        calls=calls,
        templates=templates,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
