"""대화 추천 평가. 실제 LLM을 부르므로 돌리기 전에 호출 수와 비용을 알리고 승인받는다.

    uv run python -m evals.conversation [--model gpt-6-luna] [--sets topic,similar,history]
                                        [--only t01,s01] [--out DIR]

실험 장서(525권)를 테스트 DB(TEST_DATABASE_URL)의 트랜잭션 안에 넣고, 추천 실험의 세 세트 항목을
대화로 돌린 뒤 모두 되돌린다. 개발 DB는 쓰지 않는다. 카드를 추천 실험의 라벨(같은 항목 id × 책 키)로
채점한다. 임베딩 서버가 실행 동안 필요하다(질의 인코딩. 문서 벡터는 `data/doc_vectors.json` 캐시).

결과는 `data/runs/<시각>-<모델>/`: 항목별 JSON, `items.json`(비교용),
`results-<세트>.json`(라벨 보충 도구가 읽는 형식), `summary.md`. 규칙 위반이 있으면 종료 코드 1이다.
"""

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import httpx
from alembic import command

from app.agent.models import StepKind
from app.agent.openai_client import OpenAiClient
from app.central.embedding import EmbeddingError, GuardedEmbedder
from app.central.external.tei import TeiEmbedder
from app.core.config import get_settings
from app.core.migrations import alembic_config
from app.features.children.service import related_scope as children_related_scope
from app.features.children.tools import children_extension
from app.library.hooks import register_related_scope
from app.library.librarian import PROFILE_VERSION, build_librarian_profiles
from app.seed.experiment import CollectionMissingError
from evals.collection.fetch import DATA_FILE as COLLECTION_FILE
from evals.conversation.capture import Capture, ToolCall, capturing
from evals.conversation.catalog import DATA_DIR, DOC_VECTORS, QUERY_VECTORS, load_experiment
from evals.conversation.items import ChatItem, build_items
from evals.conversation.score import ItemRun, exit_code, results, summary
from evals.librarian.__main__ import rollback_session
from evals.librarian.checks import ScenarioResult, card_ids
from evals.librarian.runner import run_scenario
from evals.recommendation.cache import CachedEmbedder
from evals.recommendation.keys import load_fields
from evals.recommendation.labels import Labels, labels_file
from evals.recommendation.sets import SEEDS_FILE, TOPIC_FILE, file_hash, load_seeds, load_topic

RUNS_DIR = DATA_DIR / "runs"
SETS = ("topic", "similar", "history")


def call_record(call: ToolCall, key_of: dict[int, str]) -> dict:
    return {
        "name": call.name,
        "input": call.input,
        "books": [key_of[i] for i in call.books if i in key_of],
        "note": call.note,
        "keyword_missing": call.keyword_missing,
    }


def item_run(
    item: ChatItem, result: ScenarioResult, calls: list[ToolCall], key_of: dict[int, str]
) -> ItemRun:
    """마지막 턴만 LLM 턴이다(고른 턴은 LLM 없음). tool 결과 앞 5권은 처음 부른 책 tool의 것."""
    assert len(result.turns) == 1, "세트 항목은 LLM 턴이 하나다"
    turn = result.last
    first = next((c for c in calls if c.books), None)
    return ItemRun(
        set_name=item.set_name,
        id=item.id,
        group=item.group,
        cards=[key_of[i] for i in card_ids(turn)],
        tool_top=[key_of[i] for i in first.books[:5]] if first else [],
        calls=[call_record(c, key_of) for c in calls],
        violations=result.violations,
        children_judged=result.children_judged,
        status=turn.status,
        llm_calls=sum(1 for s in turn.steps if s["kind"] == StepKind.LLM.value),
        input_tokens=turn.input_tokens,
        output_tokens=turn.output_tokens,
    )


def label_grades(sets: tuple[str, ...]) -> dict[str, dict[str, dict[str, int]]]:
    out = {}
    for name in SETS:
        labels = Labels(labels_file(name))
        out[name] = (
            {item_id: labels.grades(item_id) for item_id in labels.items} if name in sets else {}
        )
    return out


def label_line() -> str:
    parts = []
    for name in SETS:
        labels = Labels(labels_file(name))
        stages, by = labels.stage_counts(), labels.by_counts()
        parts.append(
            f"{name} {sum(stages.values())}("
            + ", ".join(f"{k} {v}" for k, v in stages.items())
            + "; "
            + ", ".join(f"{k} {v}" for k, v in by.items())
            + ")"
        )
    return "라벨: " + " / ".join(parts)


def set_hashes() -> dict[str, str]:
    return {"topic": file_hash(TOPIC_FILE), "seeds": file_hash(SEEDS_FILE)}


def write_run(out: Path, runs: list[ItemRun], meta: dict, text: str) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "items.json").write_text(
        json.dumps(
            {"meta": meta, "items": [asdict(r) for r in runs]}, ensure_ascii=False, indent=1
        ),
        encoding="utf-8",
    )
    for set_name, rows in results(runs).items():
        (out / f"results-{set_name}.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    (out / "summary.md").write_text(text, encoding="utf-8")


async def evaluate(
    model: str | None, sets: tuple[str, ...], only: set[str] | None, out: Path | None
) -> int:
    settings = get_settings()
    if not settings.test_database_url:
        print("TEST_DATABASE_URL이 없습니다.", file=sys.stderr)
        return 1
    try:
        fields = load_fields(COLLECTION_FILE)
    except CollectionMissingError as exc:
        print(f"{exc}. `uv run python -m evals.collection.fetch`로 받으세요.", file=sys.stderr)
        return 1
    topics = load_topic() if "topic" in sets else []
    seeds, histories = load_seeds(fields)
    seeds = seeds if "similar" in sets else []
    histories = histories if "history" in sets else []
    llm = OpenAiClient(settings.model_copy(update={"llm_model": model}) if model else settings)
    await asyncio.to_thread(command.upgrade, alembic_config(settings.test_database_url), "head")
    out = out or RUNS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}-{llm.model}"
    http = httpx.AsyncClient(
        base_url=settings.embedding_base_url, timeout=settings.embedding_timeout_seconds
    )
    encoder = CachedEmbedder(TeiEmbedder(http), QUERY_VECTORS, DOC_VECTORS)
    runs: list[ItemRun] = []
    try:
        async with rollback_session(settings.test_database_url) as session:
            try:
                catalog = await load_experiment(session, embedder=encoder)
                await encoder.check()
            except EmbeddingError as exc:
                print(
                    f"임베딩 서버가 필요합니다({exc.failure.value}). "
                    "`docker compose --profile embedding up -d embedder`",
                    file=sys.stderr,
                )
                return 1
            vectors = (
                f"벡터 {catalog.vectors}개(문서 캐시 적중 {encoder.cached_documents}, "
                f"새로 인코딩 {encoder.encoded_documents}), 인코더 {encoder.name}"
            )
            print(f"모델: {llm.model}, 장서 {len(catalog.keys)}권, {vectors}", flush=True)
            queries = GuardedEmbedder(
                encoder,
                timeout=settings.embedding_query_timeout_seconds,
                pause=settings.embedding_query_pause_seconds,
            )
            register_related_scope(children_related_scope)
            capture = Capture()
            base = build_librarian_profiles((children_extension(),))[catalog.loan_mode]
            profile = capturing(base, capture)
            items = build_items(topics, seeds, histories, catalog.keys, catalog.children)
            items = [i for i in items if only is None or i.id in only]
            for index, item in enumerate(items, start=1):
                picks = [catalog.keys[key] for key in item.picks]
                capture.take()
                result = await run_scenario(
                    session, llm, profile, catalog, item.scenario, queries, picks=picks
                )
                run = item_run(item, result, capture.take(), catalog.key_of)
                runs.append(run)
                print(
                    f"[{index}/{len(items)}] {item.set_name}/{item.id}: {run.status}, "
                    f"카드 {len(run.cards)}, tool {[c['name'] for c in run.calls]}, "
                    f"위반 {run.violations or '없음'}",
                    flush=True,
                )
    finally:
        await http.aclose()

    meta = {
        "model": llm.model,
        "profile_version": PROFILE_VERSION,
        "set_hashes": set_hashes(),
        "sets": list(sets),
        "query_encoded": encoder.encoded,
        "query_failures": queries.failures,
    }
    head = [
        f"모델 {llm.model}, 프로필 {PROFILE_VERSION}, 세트 해시 {meta['set_hashes']}",
        label_line(),
        f"{vectors}, 질의 새로 인코딩 {encoder.encoded}, 질의 인코딩 실패 {queries.failures}",
    ]
    text = summary(runs, label_grades(sets), head, llm.model)
    write_run(out, runs, meta, text)
    print(text)
    print(f"결과: {out}")
    return exit_code(runs)


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.conversation")
    parser.add_argument("--model", help="LLM 모델. 없으면 기본 모델")
    parser.add_argument("--sets", default=",".join(SETS), help="쉼표로 나눈 세트")
    parser.add_argument("--only", help="쉼표로 나눈 항목 id")
    parser.add_argument("--out", type=Path, help="결과 폴더. 없으면 data/runs/<시각>-<모델>")
    args = parser.parse_args()
    sets = tuple(s for s in args.sets.split(",") if s)
    unknown = set(sets) - set(SETS)
    if unknown:
        parser.error(f"모르는 세트: {sorted(unknown)}")
    only = set(args.only.split(",")) if args.only else None
    return asyncio.run(evaluate(args.model, sets, only, args.out))


if __name__ == "__main__":
    sys.exit(main())
