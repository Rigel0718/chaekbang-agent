"""시나리오를 대화 service로 돌린다. 평가와 표본 테스트가 함께 쓴다.

서비스와 같은 경로(`prepare_turn` → `stream_turn`)를 거쳐 개인정보 가리기, 이전 대화, 검사, 카드가
실제와 같게 돈다. 시나리오마다 새 세션이다.
"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import LlmClient
from app.agent.models import AgentRun, AgentStep, StepKind
from app.agent.profile import Profile
from app.features.children.checks import CHILDREN_TOOL_NAME
from app.features.children.rules import is_children_request
from app.library.librarian import PROFILE_NAME
from app.library.services import chat
from evals.librarian.catalog import BookState, SampleCatalog
from evals.librarian.checks import ScenarioResult, TurnResult, score
from evals.librarian.guide import guide_basis, setup_guide
from evals.librarian.scenarios import Scenario


def fill(text: str, catalog: SampleCatalog) -> str:
    """`{no_description_title}`은 소개를 지운 책, `{shelved_title}`은 서가 위치를 둔 책의 서명."""
    if "{no_description_title}" in text:
        [first, *_] = catalog.with_state(BookState.NO_DESCRIPTION)
        text = text.replace("{no_description_title}", catalog.titles[first])
    if "{shelved_title}" in text:
        assert catalog.shelved is not None, "shelve_one()을 먼저 부른다"
        text = text.replace("{shelved_title}", catalog.titles[catalog.shelved])
    return text


async def _run_facts(
    session: AsyncSession, library_id: int, run_id: int
) -> tuple[tuple[str, ...], int, int, list[dict]]:
    rows = list(
        await session.scalars(
            select(AgentStep)
            .where(AgentStep.library_id == library_id, AgentStep.run_id == run_id)
            .order_by(AgentStep.seq)
        )
    )
    tools = [s.name for s in rows if s.kind == StepKind.TOOL]
    steps = [
        {
            "seq": s.seq,
            "kind": s.kind.value,
            "name": s.name,
            "is_error": s.is_error,
            "duration_ms": s.duration_ms,
            "detail": s.detail,
        }
        for s in rows
    ]
    tokens = (
        await session.execute(
            select(AgentRun.input_tokens, AgentRun.output_tokens)
            .where(AgentRun.library_id == library_id, AgentRun.id == run_id)
            .execution_options(populate_existing=True)
        )
    ).one()
    return tuple(t for t in tools if t), tokens[0], tokens[1], steps


async def run_scenario(
    session: AsyncSession,
    llm: LlmClient,
    profile: Profile,
    catalog: SampleCatalog,
    scenario: Scenario,
) -> ScenarioResult:
    await setup_guide(session, catalog.library_id, scenario.guide)
    basis = await guide_basis(session, catalog.library_id, scenario.guide)
    session_id = None
    texts: list[str] = []
    turns: list[TurnResult] = []
    for raw in scenario.turns:
        text = fill(raw, catalog)
        prepared = await chat.prepare_turn(
            session, catalog.library_id, session_id, text, profile_name=PROFILE_NAME
        )
        session_id = prepared.session_id
        texts.append(prepared.user_text)
        stream = [e async for e in chat.stream_turn(session, llm, profile, prepared)]
        events = {e.name: e.data for e in stream}
        done = events["done"]
        tools, input_tokens, output_tokens, steps = await _run_facts(
            session, catalog.library_id, done["run_id"]
        )
        turns.append(
            TurnResult(
                text=text,
                answer=events["answer"],
                status=done["status"],
                run_id=done["run_id"],
                tools=tools,
                children=is_children_request(texts) or CHILDREN_TOOL_NAME in tools,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                steps=steps,
                progress=[e.data["text"] for e in stream if e.name == "status"],
                found=tuple(b["library_book_id"] for b in events.get("found", {}).get("books", [])),
            )
        )
    if session_id is not None:
        await chat.end_session(session, catalog.library_id, session_id)
    return score(ScenarioResult(scenario, turns, guide_basis=basis), catalog)


async def run_scenarios(
    session: AsyncSession,
    llm: LlmClient,
    profile: Profile,
    catalog: SampleCatalog,
    scenarios: Sequence[Scenario],
) -> list[ScenarioResult]:
    return [await run_scenario(session, llm, profile, catalog, s) for s in scenarios]
