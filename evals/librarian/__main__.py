"""AI 사서 평가. 실제 LLM을 부르므로 돌리기 전에 알린다.

    uv run python -m evals.librarian [--model gpt-6-luna] [--only dinosaur,not-held] [--out DIR]
                                     [--no-vectors]

시나리오가 끝날 때마다 진행을 출력하고 `<DIR>/NN-<id>.json`에 저장한다. 끝나면 `summary.md`를 쓴다.
기본 위치는 `evals/librarian/data/runs/<시각>-<모델>/`이다. 답에 표본 서지가 들어 있어 저장소에서
뺀 폴더에 둔다.

테스트 DB(TEST_DATABASE_URL)의 트랜잭션 안에서 표본을 적재해 돌리고 되돌린다. 개발 DB는 쓰지 않는다.
서지는 실제 값이지만 기관과 사본 상태는 가상이므로 수치를 실제 서비스 성능으로 쓰지 않는다.
규칙 위반이나 기대 불일치가 있으면 실패(종료 코드 1)한다.

표본을 넣을 때 벡터 두 층도 넣는다. 문서 벡터는 `data/doc_vectors.json`에 캐시해 처음 한 번만 임베딩
서버로 인코딩한다. 평가 중 질의는 LLM 낱말이 실행마다 달라 임베딩 서버가 필요하고, 같은 질의는
`data/query_vectors.json`에서 꺼낸다. `--no-vectors`는 벡터 없이(서버 없이) 돌린다.
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

import httpx
from alembic import command
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.agent.openai_client import OpenAiClient
from app.central.embedding import EmbeddingError, GuardedEmbedder
from app.central.external.tei import TeiEmbedder
from app.core.config import get_settings
from app.core.migrations import alembic_config
from app.features.children.service import related_scope as children_related_scope
from app.features.children.tools import children_extension
from app.library.hooks import register_related_scope
from app.library.librarian import build_librarian_profiles
from evals.librarian.catalog import (
    DATA_FILE,
    DOC_VECTORS,
    QUERY_VECTORS,
    SampleMissingError,
    load_catalog,
    load_sample,
)
from evals.librarian.checks import ScenarioResult, card_ids, fallback_ratio, guide_metrics
from evals.librarian.guide import fixed_clock, shelve_one
from evals.librarian.runner import run_scenario
from evals.librarian.scenarios import SCENARIOS
from evals.recommendation.cache import CachedEmbedder

RUNS_DIR = DATA_FILE.parent / "runs"
CHECKS = (
    "not_held",
    "children_general",
    "asks_personal",
    "invented_title",
    "invented_guide",
    "invented_basis",
)
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


@asynccontextmanager
async def _clock() -> AsyncIterator[None]:
    """안내 평가의 날짜 고정(evals/librarian/guide.py). 평가 전체에 건다."""
    with fixed_clock():
        yield


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
        "topic_met": result.topic_met,
        "violations": result.violations,
        "turns": [asdict(turn) for turn in result.turns],
        "guide_basis": result.guide_basis,  # 안내 판정의 기준값(가상 평가 안내와 계산된 일정)
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


def eval_encoder(http: httpx.AsyncClient) -> CachedEmbedder:
    """평가 인코더: 임베딩 서버 앞에 문서·질의 벡터 캐시."""
    return CachedEmbedder(TeiEmbedder(http), QUERY_VECTORS, DOC_VECTORS)


def vector_line(encoder: CachedEmbedder | None, vectors: int) -> str:
    if encoder is None:
        return "벡터: 넣지 않음(--no-vectors)"
    return (
        f"벡터: {vectors}개 적재(문서 캐시 적중 {encoder.cached_documents}, "
        f"새로 인코딩 {encoder.encoded_documents}), 인코더 {encoder.name}"
    )


async def evaluate(
    model: str | None, only: set[str] | None, out: Path | None, vectors: bool = True
) -> int:
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
    http = httpx.AsyncClient(
        base_url=settings.embedding_base_url, timeout=settings.embedding_timeout_seconds
    )
    encoder = eval_encoder(http) if vectors else None
    async with rollback_session(settings.test_database_url) as session, _clock():
        try:
            catalog = await load_catalog(session, sample, embedder=encoder)
        except EmbeddingError as exc:
            await http.aclose()
            print(
                f"표본 벡터를 넣지 못했습니다({exc.failure.value}). 임베딩 서버를 켜거나 "
                "(`docker compose --profile embedding up -d embedder`) --no-vectors로 돌리세요.",
                file=sys.stderr,
            )
            return 1
        print(vector_line(encoder, catalog.vectors), flush=True)
        # 서버와 같은 질의 인코더(시간 제한, 쉬기). 실패하면 검색이 키워드 순위로 내려가므로 센다
        queries = None
        if encoder is not None:
            queries = GuardedEmbedder(
                encoder,
                timeout=settings.embedding_query_timeout_seconds,
                pause=settings.embedding_query_pause_seconds,
            )
            try:
                await encoder.check()
            except EmbeddingError as exc:
                await http.aclose()
                print(f"임베딩 서버를 확인하지 못했습니다({exc.failure.value}).", file=sys.stderr)
                return 1
        await shelve_one(session, catalog)
        # 서버(`app/main.py`)와 같은 기관 개별 기능을 조립한다
        register_related_scope(children_related_scope)
        # 시나리오마다 그 운영 방식의 프로필을 쓴다(실행기가 평가 기관의 방식도 맞춘다)
        profiles = build_librarian_profiles((children_extension(),))
        for index, scenario in enumerate(scenarios, start=1):
            profile = profiles[scenario.loan_mode]
            result = await run_scenario(session, llm, profile, catalog, scenario, queries)
            results.append(result)
            path = out / f"{index:02d}-{scenario.id}.json"
            path.write_text(
                json.dumps(_record(index, result), ensure_ascii=False, indent=1, default=str),
                encoding="utf-8",
            )
            print(_progress(index, len(scenarios), result), flush=True)
    await http.aclose()

    turns = [t for r in results for t in r.turns]
    violations = sum(len(v) for r in results for v in r.violations.values())
    missed = [r.scenario.id for r in results if not r.expectation_met]
    metrics = guide_metrics(results)
    lines = [
        f"표본: {len(sample.books)}권 (받은 날 {sample.fetched_on}), 모델: {llm.model}",
        f"어린이 도서: {len(catalog.children)}권, 추천 가능: {len(catalog.recommendable)}권",
        vector_line(encoder, catalog.vectors)
        + (
            f", 질의 새로 인코딩 {encoder.encoded}, 질의 인코딩 실패 {queries.failures}"
            if encoder and queries
            else ""
        ),
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
        f"안내 질문 {metrics['guide_questions']}개: 안내 tool 사용률 "
        f"{metrics['guide_tool_rate'] * 100:.0f}%, 책 tool 호출 "
        f"{metrics['book_tool_calls_in_guide_questions']}번",
        f"찾은 책 카드 턴 {metrics['found_turns']}개 중 find_book 다시 부름 "
        f"{metrics['find_book_after_found']}번",
        "날짜는 2026-11-11 14:00(기관 시간대)으로 고정했다. 안내는 가상이다.",
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
    parser.add_argument("--no-vectors", action="store_true", help="표본에 벡터를 넣지 않는다")
    args = parser.parse_args()
    only = set(args.only.split(",")) if args.only else None
    return asyncio.run(evaluate(args.model, only, args.out, vectors=not args.no_vectors))


if __name__ == "__main__":
    sys.exit(main())
