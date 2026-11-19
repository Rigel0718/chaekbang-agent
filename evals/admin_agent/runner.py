"""시나리오를 운영 에이전트 대화 service로 돌린다. 서비스와 같은 경로(`prepare_admin_turn` →
`stream_admin_turn`)를 거쳐 가리기, 프로필, 기록이 실제와 같게 돈다. 시나리오마다 새 세션이다.

tool 결과는 실행 기록에 없다. 그래서 단계 기록의 입력(분석 tool은 입력을 모두 남긴다)으로 같은
tool을 다시 불러 결과를 구한다. 같은 데이터에서 같은 결과다.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import LlmClient
from app.agent.models import AgentRun, AgentStep, StepKind
from app.agent.profile import Profile
from app.agent.tools import ToolContext
from app.library.admin_agent import PROFILE_NAME
from app.library.models.library import LoanMode
from app.library.services import admin_chat
from evals.admin_agent.fixture import EvalLibraries
from evals.admin_agent.scenarios import Scenario
from evals.admin_agent.score import ToolCallRecord, TurnRecord


async def _calls(
    session: AsyncSession, library_id: int, run_id: int, profile: Profile
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
    tools = {t.name: t for t in profile.tools}
    calls = []
    for step in steps:
        args = step.detail or {}
        result = None
        tool = tools.get(step.name or "")
        if tool is not None and not step.is_error:
            data = tool.input_model.model_validate(args)
            result = await tool.handler(ToolContext(library_id, session), data)
        calls.append(ToolCallRecord(step.name or "", args, step.is_error, result))
    tokens = (
        await session.execute(
            select(AgentRun.input_tokens, AgentRun.output_tokens)
            .where(AgentRun.library_id == library_id, AgentRun.id == run_id)
            .execution_options(populate_existing=True)
        )
    ).one()
    return calls, tokens[0], tokens[1]


async def run_scenario(
    session: AsyncSession,
    llm: LlmClient,
    profiles: dict[LoanMode, Profile],
    libraries: EvalLibraries,
    scenario: Scenario,
) -> TurnRecord:
    internal = scenario.loan_mode == LoanMode.INTERNAL
    library_id = libraries.internal_id if internal else libraries.external_id
    profile = profiles[scenario.loan_mode]
    prepared = await admin_chat.prepare_admin_turn(
        session, library_id, None, scenario.question, profile_name=PROFILE_NAME
    )
    events = {
        e.name: e.data async for e in admin_chat.stream_admin_turn(session, llm, profile, prepared)
    }
    answer, done = events["answer"], events["done"]
    calls, input_tokens, output_tokens = await _calls(session, library_id, done["run_id"], profile)
    return TurnRecord(
        question=scenario.question,
        message=answer["message"],
        unsupported=answer["unsupported"],
        status=done["status"],
        calls=calls,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
