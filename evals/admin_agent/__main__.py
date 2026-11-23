"""운영 에이전트 평가. 실제 LLM을 부르므로 돌리기 전에 호출 수와 비용을 알리고 승인을 받는다.

    uv run python -m evals.admin_agent [--model gpt-6-luna] [--only total,kids-science] [--out DIR]

테스트 DB(TEST_DATABASE_URL)의 트랜잭션 안에 평가 기관(`fixture.py`)을 넣어 돌리고 되돌린다. 개발
DB는 쓰지 않는다. 날짜는 2026-11-19로 고정한다. 시나리오마다 `<DIR>/NN-<id>.json`을, 끝나면
`summary.md`를 쓴다. 기본 위치는 `evals/admin_agent/data/runs/<시각>-<모델>/`이다(저장소에서 뺀
폴더). 하나라도 틀리면 종료 코드 1이다. 임베딩 서버는 쓰지 않는다.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from alembic import command
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.agent.llm import LlmClient
from app.core.config import get_settings
from app.core.migrations import alembic_config
from app.features.children.analytics import admin_extension
from app.library.admin_agent import PROFILE_VERSION, build_admin_profiles
from evals.admin_agent.fixture import build_libraries, fixed_clock
from evals.admin_agent.runner import run_scenario
from evals.admin_agent.scenarios import SCENARIOS, Scenario
from evals.admin_agent.score import Score, TurnRecord, score

DATA_DIR = Path(__file__).parent / "data"
RUNS_DIR = DATA_DIR / "runs"
METRICS = ("tool_ok", "numbers_ok", "unsupported_ok", "draft_ok")
METRIC_NAMES = {
    "tool_ok": "tool 선택",
    "numbers_ok": "숫자 충실도",
    "unsupported_ok": "못 하는 분석 분류",
    "draft_ok": "초안 충실도",
}


@asynccontextmanager
async def rollback_session(url: str) -> AsyncIterator[AsyncSession]:
    """끝나면 모든 변경을 되돌리는 세션. service의 commit은 savepoint로 처리된다."""
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            trans = await conn.begin()
            session = AsyncSession(
                bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
            )
            try:
                yield session
            finally:
                await session.close()
                await trans.rollback()
    finally:
        await engine.dispose()


def _record(index: int, scenario: Scenario, turn: TurnRecord, result: Score) -> dict:
    return {
        "index": index,
        "id": scenario.id,
        "traces": list(scenario.traces),
        "question": scenario.question,
        "expected": {
            "calls": [[asdict(c) for c in options] for options in scenario.calls],
            "must_say": list(scenario.must_say),
            "unsupported": scenario.unsupported,
            "draft": scenario.draft,
            "notice": scenario.notice,
            "purchase": scenario.purchase,
        },
        "score": asdict(result),
        "turn": asdict(turn),
    }


def _mark(ok: bool) -> str:
    return "맞음" if ok else "틀림"


def _line(scenario: Scenario, turn: TurnRecord, result: Score) -> str:
    notes = []
    if result.missing_calls:
        notes.append(f"빠진 호출 {result.missing_calls}")
    if result.missing_say:
        notes.append(f"빠진 값 {result.missing_say}")
    if result.invented:
        notes.append(f"결과에 없는 숫자 {result.invented}")
    if result.present_absent:
        notes.append(f"없어야 할 값 {result.present_absent}")
    if result.draft_notes:
        notes.append(f"초안 {result.draft_notes}")
    return (
        f"| {scenario.id} | {turn.status} | {_mark(result.tool_ok)} | {_mark(result.numbers_ok)} "
        f"| {_mark(result.unsupported_ok)} | {_mark(result.draft_ok)} | {'; '.join(notes)} |"
    )


def summary_lines(model: str, rows: Sequence[tuple[Scenario, TurnRecord, Score]]) -> list[str]:
    total = len(rows)
    counts = {m: sum(1 for _, _, s in rows if getattr(s, m)) for m in METRICS}
    return [
        f"모델: {model}, 프로필: admin {PROFILE_VERSION}, 시나리오 {total}개",
        "평가 기관은 가상이다(2026-11-19 고정). 수치를 실제 서비스 성능으로 쓰지 않는다.",
        "",
        *(f"- {METRIC_NAMES[m]}: {counts[m]}/{total}" for m in METRICS),
        f"- 모두 맞음: {sum(1 for _, _, s in rows if s.passed)}/{total}",
        "",
        "| 시나리오 | 상태 | tool 선택 | 숫자 충실도 | 못 하는 분석 | 초안 | 메모 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
        *(_line(sc, turn, result) for sc, turn, result in rows),
        "",
        f"입력 토큰 {sum(t.input_tokens for _, t, _ in rows)}, "
        f"출력 토큰 {sum(t.output_tokens for _, t, _ in rows)}",
    ]


async def run_all(
    llm: LlmClient, scenarios: Sequence[Scenario], out: Path, database_url: str
) -> list[tuple[Scenario, TurnRecord, Score]]:
    """평가 기관을 넣고 시나리오를 돌린 뒤 되돌린다. 결과 파일과 요약을 out에 쓴다."""
    await asyncio.to_thread(out.mkdir, parents=True, exist_ok=True)
    profiles = build_admin_profiles((admin_extension(),))  # 서버(`app/main.py`)와 같은 조립
    rows: list[tuple[Scenario, TurnRecord, Score]] = []
    async with rollback_session(database_url) as session:
        with fixed_clock():
            libraries = await build_libraries(session)
            for index, scenario in enumerate(scenarios, start=1):
                turn = await run_scenario(session, llm, profiles, libraries, scenario)
                result = score(scenario, turn)
                rows.append((scenario, turn, result))
                path = out / f"{index:02d}-{scenario.id}.json"
                path.write_text(
                    json.dumps(
                        _record(index, scenario, turn, result),
                        ensure_ascii=False,
                        indent=1,
                        default=str,
                    ),
                    encoding="utf-8",
                )
                print(
                    f"[{index}/{len(scenarios)}] {scenario.id}: {_line(scenario, turn, result)}\n"
                    f"    답: {turn.message}",
                    flush=True,
                )
    lines = summary_lines(getattr(llm, "model", "?"), rows)
    (out / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return rows


async def evaluate(model: str | None, only: set[str] | None, out: Path | None) -> int:
    from app.agent.openai_client import OpenAiClient

    settings = get_settings()
    if not settings.test_database_url:
        print("TEST_DATABASE_URL이 없습니다.", file=sys.stderr)
        return 1
    scenarios = [s for s in SCENARIOS if only is None or s.id in only]
    llm_settings = settings.model_copy(update={"llm_model": model}) if model else settings
    llm = OpenAiClient(llm_settings)
    await asyncio.to_thread(command.upgrade, alembic_config(settings.test_database_url), "head")
    out = out or RUNS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{llm.model}"
    print(f"모델: {llm.model}, 시나리오 {len(scenarios)}개, 결과: {out}", flush=True)
    rows = await run_all(llm, scenarios, out, settings.test_database_url)
    return 0 if all(result.passed for _, _, result in rows) else 1


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.admin_agent")
    parser.add_argument("--model", help="LLM 모델. 없으면 기본 모델")
    parser.add_argument("--only", help="쉼표로 나눈 시나리오 id")
    parser.add_argument("--out", type=Path, help="결과 폴더. 없으면 data/runs/<시각>-<모델>")
    args = parser.parse_args()
    only = set(args.only.split(",")) if args.only else None
    return asyncio.run(evaluate(args.model, only, args.out))


if __name__ == "__main__":
    sys.exit(main())
