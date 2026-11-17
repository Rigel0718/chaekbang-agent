"""시나리오를 대화 service로 돌린다. 평가와 표본 테스트가 함께 쓴다.

서비스와 같은 경로(`prepare_turn` → `stream_turn`)를 거쳐 개인정보 가리기, 이전 대화, 검사, 카드가
실제와 같게 돈다. 시나리오마다 새 세션이다.

관련 책 tool의 결과는 실행 기록에 없다. 그래서 단계 기록의 입력(책 id 또는 null)으로 같은 service를
다시 불러 결과의 책을 구한다(같은 데이터에서 같은 결과).
"""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import LlmClient
from app.agent.models import AgentRun, AgentStep, StepKind
from app.agent.profile import Profile
from app.central.embedding import Embedder
from app.features.children.checks import CHILDREN_TOOL_NAMES
from app.features.children.rules import is_children_request
from app.features.children.service import children_book_ids
from app.library.librarian import PROFILE_NAME
from app.library.services import chat
from app.library.services.related import related_for_session, similar_for_book
from evals.librarian.catalog import BookState, SampleCatalog
from evals.librarian.checks import RELATED_TOOLS, ScenarioResult, TurnResult, score
from evals.librarian.guide import guide_basis, setup_guide
from evals.librarian.scenarios import Picked, Scenario


def fill(text: str, catalog: SampleCatalog) -> str:
    """`{no_description_title}`은 소개를 지운 책, `{shelved_title}`은 서가 위치를 둔 책의 서명."""
    if "{no_description_title}" in text:
        [first, *_] = catalog.with_state(BookState.NO_DESCRIPTION)
        text = text.replace("{no_description_title}", catalog.titles[first])
    if "{children_title}" in text:
        text = text.replace("{children_title}", catalog.titles[catalog.children_pick])
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


def _picked(scenario: Scenario, catalog: SampleCatalog) -> int | None:
    if scenario.selected is Picked.SHELVED:
        assert catalog.shelved is not None, "shelve_one()을 먼저 부른다"
        return catalog.shelved
    if scenario.selected is Picked.CHILDREN:
        return catalog.children_pick
    return None


async def _related(
    session: AsyncSession, library_id: int, session_id, steps: list[dict]
) -> tuple[tuple[int | None, ...], tuple[int, ...]]:
    """관련 책 tool의 입력과, 같은 service로 다시 구한 결과의 책(입력 순서, 서로 다른 책)."""
    inputs: list[int | None] = []
    found: list[int] = []
    for step in steps:
        if step["name"] not in RELATED_TOOLS or step["is_error"]:
            continue
        book_id = (step["detail"] or {}).get("library_book_id")
        within = children_book_ids(library_id) if step["name"] != RELATED_TOOLS[0] else None
        if book_id is None:
            history = await chat.session_books(session, library_id, session_id)
            items = await related_for_session(session, library_id, history, within=within)
        else:
            items = await similar_for_book(session, library_id, book_id, within=within)
        inputs.append(book_id)
        found += [i.candidate.library_book.id for i in items]
    return tuple(inputs), tuple(dict.fromkeys(found))


async def run_scenario(
    session: AsyncSession,
    llm: LlmClient,
    profile: Profile,
    catalog: SampleCatalog,
    scenario: Scenario,
    encoder: Embedder | None = None,
    picks: Sequence[int] = (),
) -> ScenarioResult:
    """picks는 첫 턴 전에 차례로 고를 책이다(대화 추천 평가의 기준 책·최근 기록)."""
    await setup_guide(session, catalog.library_id, scenario.guide)
    basis = await guide_basis(session, catalog.library_id, scenario.guide)
    session_id = None
    texts: list[str] = []
    turns: list[TurnResult] = []
    picked = _picked(scenario, catalog)
    selected = tuple(picks) if picked is None else (picked, *picks)
    for book_id in selected:
        prepared = await chat.prepare_turn(
            session,
            catalog.library_id,
            session_id,
            None,
            profile_name=PROFILE_NAME,
            selected_id=book_id,
        )
        session_id = prepared.session_id
        _ = [e async for e in chat.stream_turn(session, llm, profile, prepared)]  # LLM 없음
    for raw in scenario.turns:
        text = fill(raw, catalog)
        prepared = await chat.prepare_turn(
            session, catalog.library_id, session_id, text, profile_name=PROFILE_NAME
        )
        session_id = prepared.session_id
        texts.append(prepared.user_text)
        stream = [e async for e in chat.stream_turn(session, llm, profile, prepared, encoder)]
        events = {e.name: e.data for e in stream}
        done = events["done"]
        tools, input_tokens, output_tokens, steps = await _run_facts(
            session, catalog.library_id, done["run_id"]
        )
        related_inputs, related = await _related(session, catalog.library_id, session_id, steps)
        turns.append(
            TurnResult(
                text=text,
                answer=events["answer"],
                status=done["status"],
                run_id=done["run_id"],
                tools=tools,
                children=is_children_request(texts) or bool(CHILDREN_TOOL_NAMES & set(tools)),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                steps=steps,
                progress=[e.data["text"] for e in stream if e.name == "status"],
                found=tuple(b["library_book_id"] for b in events.get("found", {}).get("books", [])),
                selected=selected,
                related_inputs=related_inputs,
                related=related,
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
    encoder: Embedder | None = None,
) -> list[ScenarioResult]:
    return [await run_scenario(session, llm, profile, catalog, s, encoder) for s in scenarios]
