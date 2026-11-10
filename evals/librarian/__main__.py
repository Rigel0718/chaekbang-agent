"""AI 사서 평가. 실제 LLM을 부르므로 돌리기 전에 알린다.

    uv run python -m evals.librarian [--model gpt-6-luna] [--only dinosaur,not-held] [--out DIR]

시나리오가 끝날 때마다 진행을 출력하고 `<DIR>/NN-<id>.json`에 저장한다. 끝나면 `summary.md`를 쓴다.
기본 위치는 `evals/librarian/data/runs/<시각>-<모델>/`이다. 답에 표본 서지가 들어 있어 저장소에서
뺀 폴더에 둔다.

테스트 DB(TEST_DATABASE_URL)의 트랜잭션 안에서 표본을 적재해 돌리고 되돌린다. 개발 DB는 쓰지 않는다.
서지는 실제 값이지만 기관과 사본 상태는 가상이므로 수치를 실제 서비스 성능으로 쓰지 않는다.
규칙 위반이나 기대 불일치가 있으면 실패(종료 코드 1)한다.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from alembic import command
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.agent.openai_client import OpenAiClient
from app.core.config import get_settings
from app.core.migrations import alembic_config
from app.features.children.tools import children_extension
from app.library.librarian import build_librarian_profiles
from evals.librarian.catalog import DATA_FILE, SampleMissingError, load_catalog, load_sample
from evals.librarian.checks import ScenarioResult, card_ids, fallback_ratio
from evals.librarian.runner import run_scenario
from evals.librarian.scenarios import SCENARIOS

RUNS_DIR = DATA_FILE.parent / "runs"
CHECKS = ("not_held", "children_general", "asks_personal", "invented_title")
HEADER = "| 시나리오 | 상태 | 추천 | 어린이 판단 | 기대 | " + " | ".join(CHECKS) + " |"


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


def _line(result: ScenarioResult) -> str:
    turn = result.last
    counts = [str(len(result.violations.get(name, []))) for name in CHECKS]
    return (
        f"| {result.scenario.id} | {'/'.join(t.status for t in result.turns)} "
        f"| {len(card_ids(turn))} | {'어린이' if result.children_judged else '일반'} "
        f"| {'맞음' if result.expectation_met else '틀림'} | " + " | ".join(counts) + " |"
    )


def _record(index: int, result: ScenarioResult) -> dict:
    scenario = result.scenario
    return {
        "index": index,
        "id": scenario.id,
        "traces": list(scenario.traces),
        "expect": scenario.expect.value,
        "expected_children": scenario.children,
        "topic": scenario.topic,
        "children_judged": result.children_judged,
        "expectation_met": result.expectation_met,
        "violations": result.violations,
        "turns": [asdict(turn) for turn in result.turns],
    }


def _progress(index: int, total: int, result: ScenarioResult) -> str:
    turn = result.last
    titles = [c["title"] for c in turn.answer["recommendations"]]
    tokens = sum(t.input_tokens for t in result.turns), sum(t.output_tokens for t in result.turns)
    flags = "위반 " + str(result.violations) if result.violations else "위반 없음"
    return (
        f"[{index}/{total}] {result.scenario.id}: {'/'.join(t.status for t in result.turns)}, "
        f"기대 {'맞음' if result.expectation_met else '틀림'}, {flags}, "
        f"tool {list(turn.tools)}, 토큰 {tokens[0]}/{tokens[1]}\n"
        f"    답: {turn.answer['message']}\n    추천: {titles}"
    )


def _summary(lines: list[str]) -> str:
    return "\n".join(lines) + "\n"


async def evaluate(model: str | None, only: set[str] | None, out: Path | None) -> int:
    settings = get_settings()
    if not settings.test_database_url:
        print("TEST_DATABASE_URL이 없습니다.", file=sys.stderr)
        return 1
    try:
        sample = load_sample()
    except SampleMissingError as exc:
        print(exc, file=sys.stderr)
        return 1
    scenarios = [s for s in SCENARIOS if only is None or s.id in only]
    llm_settings = settings.model_copy(update={"llm_model": model}) if model else settings
    llm = OpenAiClient(llm_settings)
    await asyncio.to_thread(command.upgrade, alembic_config(settings.test_database_url), "head")
    out = out or RUNS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{llm.model}"
    out.mkdir(parents=True, exist_ok=True)
    print(f"모델: {llm.model}, 시나리오 {len(scenarios)}개, 결과: {out}", flush=True)
    results: list[ScenarioResult] = []
    async with rollback_session(settings.test_database_url) as session:
        catalog = await load_catalog(session, sample)
        profile = build_librarian_profiles((children_extension(),))[catalog.loan_mode]
        for index, scenario in enumerate(scenarios, start=1):
            result = await run_scenario(session, llm, profile, catalog, scenario)
            results.append(result)
            path = out / f"{index:02d}-{scenario.id}.json"
            path.write_text(
                json.dumps(_record(index, result), ensure_ascii=False, indent=1, default=str),
                encoding="utf-8",
            )
            print(_progress(index, len(scenarios), result), flush=True)

    turns = [t for r in results for t in r.turns]
    violations = sum(len(v) for r in results for v in r.violations.values())
    missed = [r.scenario.id for r in results if not r.expectation_met]
    lines = [
        f"표본: {len(sample.books)}권 (받은 날 {sample.fetched_on}), 모델: {llm.model}",
        f"어린이 도서: {len(catalog.children)}권, 추천 가능: {len(catalog.recommendable)}권",
        "기관과 사본 상태는 가상이다. 수치를 실제 서비스 성능으로 쓰지 않는다.",
        "",
        HEADER,
        "|" + " --- |" * (5 + len(CHECKS)),
        *(_line(r) for r in results),
        "",
        f"턴 {len(turns)}개, 입력 토큰 {sum(t.input_tokens for t in turns)}, "
        f"출력 토큰 {sum(t.output_tokens for t in turns)}, "
        f"고정 답 비율 {fallback_ratio(results) * 100:.1f}%",
        f"규칙 위반 {violations}건, 기대 불일치 {len(missed)}건 {missed if missed else ''}",
    ]
    (out / "summary.md").write_text(_summary(lines), encoding="utf-8")
    print(_summary(lines))
    for result in results:
        for name, items in result.violations.items():
            print(f"- {result.scenario.id} {name}: {items}", file=sys.stderr)
    return 1 if violations or missed else 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.librarian")
    parser.add_argument("--model", help="LLM 모델. 없으면 LLM_MODEL")
    parser.add_argument("--only", help="쉼표로 나눈 시나리오 id")
    parser.add_argument("--out", type=Path, help="결과 폴더. 없으면 data/runs/<시각>-<모델>")
    args = parser.parse_args()
    only = set(args.only.split(",")) if args.only else None
    return asyncio.run(evaluate(args.model, only, args.out))


if __name__ == "__main__":
    sys.exit(main())
