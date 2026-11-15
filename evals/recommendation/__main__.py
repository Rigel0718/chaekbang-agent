"""추천 실험 실행. LLM과 외부 API를 부르지 않는다.

    uv run python -m evals.recommendation topic [--variants a,b,…] [--split tune|check|all]
                                                [--reference <변형>]

개발 DB(`DATABASE_URL`)의 실험 기관(`실험용 가상 작은도서관`, 이름으로 찾는다)에서 읽기만 한다.
같은 평가 세트(`sets/topic.json`)와 라벨(`data/labels/topic.json`)로 변형을 나란히 잰다.

- 질의 인코딩만 로컬 임베딩 서버를 쓴다. 질의 벡터는 `data/query_vectors.json`에 캐시해, 캐시가
  다 차 있으면 서버 없이 돈다.
- 어린이 요청에는 어린이 도서 조건을 코드가 넘긴다. 결과에 추천할 수 없는 책이나 어린이 요청의
  일반 도서가 있으면 위반으로 세고 종료 코드가 1이다.
- 결과는 `data/runs/<시각>/`에 쓴다(`summary.md`, `results.json`). 책 키가 실험 장서를 가리켜
  저장소에서 뺀 폴더다. 같은 데이터에서 같은 명령은 시각과 걸린 시간 줄만 빼고 요약이 같다.
- 장서는 YES24 스테디셀러이고 기관은 가상이다. 수치를 실제 서비스 성능으로 쓰지 않는다.

종료 코드: 0 완료, 1 전제 조건·인자 문제나 규칙 위반, 2 임베딩 서버 장애.
"""

import argparse
import asyncio
import json
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.central.embedding import Embedder, EmbeddingError
from app.central.external.tei import TeiEmbedder
from app.central.models import Book, OfficialBookEmbedding
from app.core.config import get_settings
from app.features.children.service import children_book_ids
from app.library.models.catalog import LibraryBook
from app.library.models.embedding import BookEmbedding
from app.library.models.library import Library
from app.library.recommendation.authors import writer_keys_sql
from app.library.recommendation.search import recommendable_ids
from app.seed.experiment import LIBRARY_NAME, CollectionMissingError
from evals.collection.fetch import DATA_FILE as COLLECTION_FILE
from evals.recommendation.cache import CachedEmbedder
from evals.recommendation.keys import DATA_DIR, HOLDOUT_FIELDS, library_keys, load_fields
from evals.recommendation.labels import Labels, labels_file
from evals.recommendation.metrics import QueryScore, compare, mean, score_query
from evals.recommendation.sets import TOPIC_FILE, SetError, TopicQuery, file_hash, load_topic
from evals.recommendation.variants import DEFAULT_VARIANTS, VARIANTS, Variant, run_variant

RUNS_DIR = DATA_DIR / "runs"
EXIT_OK = 0
EXIT_PRECONDITION = 1
EXIT_STOPPED = 2
SPLIT_NAMES = {"tune": "조정", "check": "확인"}
GROUPS = (
    ("어린이", lambda q: q.children),
    ("일반", lambda q: not q.children),
    ("주제어", lambda q: q.style == "topic"),
    ("상황", lambda q: q.style == "mood"),
)
VOLATILE = ("시각:", "걸린 시간")  # 요약에서 실행마다 달라지는 줄의 머리


def git_state() -> str:
    """커밋과 고친 파일 여부. 요약의 지문에 적는다."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "status", "--porcelain"], capture_output=True, text=True, check=True
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "알 수 없음"
    return f"{commit}{' + 고친 파일 있음' if dirty else ''}"


async def _vector_counts(session: AsyncSession, library_id: int) -> list[str]:
    """실험 기관 범위의 모델·텍스트 버전·종류별 벡터 수(두 층 합)."""
    official = await session.execute(
        select(
            OfficialBookEmbedding.model_name,
            OfficialBookEmbedding.text_version,
            OfficialBookEmbedding.kind,
            func.count(),
        )
        .join(LibraryBook, LibraryBook.book_id == OfficialBookEmbedding.book_id)
        .where(LibraryBook.library_id == library_id)
        .group_by(
            OfficialBookEmbedding.model_name,
            OfficialBookEmbedding.text_version,
            OfficialBookEmbedding.kind,
        )
    )
    own = await session.execute(
        select(
            BookEmbedding.model_name, BookEmbedding.text_version, BookEmbedding.kind, func.count()
        )
        .where(BookEmbedding.library_id == library_id)
        .group_by(BookEmbedding.model_name, BookEmbedding.text_version, BookEmbedding.kind)
    )
    counts: dict[tuple, int] = {}
    for model, version, kind, count in [*official, *own]:
        counts[(model, version, kind)] = counts.get((model, version, kind), 0) + count
    return [
        f"{model} v{version} {kind}: {count}"
        for (model, version, kind), count in sorted(counts.items())
    ]


async def _groups(
    session: AsyncSession, library_id: int, ids: Sequence[int]
) -> dict[int, tuple[list[str], list[str]]]:
    """기관 도서 id → (지은이 키, 시리즈 키). 겹침 지표에 쓴다."""
    rows = await session.execute(
        select(LibraryBook.id, writer_keys_sql(), Book.series_keys)
        .outerjoin(Book, Book.id == LibraryBook.book_id)
        .where(LibraryBook.library_id == library_id, LibraryBook.id.in_(list(ids)))
    )
    return {book_id: (list(authors or []), list(series or [])) for book_id, authors, series in rows}


def _settings_line(variant: Variant) -> str:
    if variant.settings is None:
        return f"- `{variant.name}`: {variant.note}"
    values = asdict(variant.settings)
    values["weights"] = {kind.value: weight for kind, weight in variant.settings.weights.items()}
    values.pop("limit")
    return f"- `{variant.name}`: {variant.note} — {json.dumps(values, ensure_ascii=False)}"


def _table(
    names: Sequence[str],
    scores: Mapping[str, Mapping[str, QueryScore]],
    queries: Sequence[TopicQuery],
    reference: str,
) -> list[str]:
    lines = [
        "| 변형 | 질의 | nDCG@5 | Hit@5 | Recall@10 | 겹침 | 라벨 없음 "
        "| 차이 | 이김·비김·짐 | 95% 구간 |",
        "|" + " --- |" * 10,
    ]
    ids = [q.id for q in queries]
    base = [scores[reference][i].ndcg for i in ids]
    for name in names:
        rows = [scores[name][i] for i in ids]
        versus = "기준 | - | -"
        if name != reference:
            c = compare(base, [row.ndcg for row in rows])
            versus = (
                f"{c.mean_diff:+.3f} | {c.wins}·{c.ties}·{c.losses} | {c.low:+.3f} ~ {c.high:+.3f}"
            )
        lines.append(
            f"| {name} | {len(rows)} | {mean([r.ndcg for r in rows]):.3f}"
            f" | {mean([r.hit for r in rows]):.3f} | {mean([r.recall for r in rows]):.3f}"
            f" | {mean([r.overlap for r in rows]):.2f} | {sum(r.unlabeled for r in rows)}"
            f" | {versus} |"
        )
    return lines


def _write(out: Path, summary: str, results: dict) -> None:
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.md").write_text(summary, encoding="utf-8")
    (out / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8"
    )


def stable(summary: str) -> str:
    """요약에서 실행마다 달라지는 줄(시각, 걸린 시간)을 뺀 것. 두 실행을 비교할 때 쓴다."""
    return "\n".join(line for line in summary.splitlines() if not line.startswith(VOLATILE))


async def run_topic(
    session: AsyncSession,
    embedder: Embedder,
    *,
    queries: Sequence[TopicQuery],
    labels: Labels,
    out: Path,
    variant_names: Sequence[str] = DEFAULT_VARIANTS,
    variants: Mapping[str, Variant] = VARIANTS,
    split: str = "all",
    reference: str | None = None,
    library_name: str = LIBRARY_NAME,
    fingerprint: Sequence[str] = (),
    fields: Mapping[str, str] | None = None,
) -> int:
    """변형들을 주제 질의에 돌려 요약과 질의별 결과를 쓰고 종료 코드를 돌려준다."""
    unknown = [name for name in variant_names if name not in variants]
    if unknown:
        print(f"없는 변형: {', '.join(unknown)}\n쓸 수 있는 변형: {', '.join(variants)}")
        return EXIT_PRECONDITION
    reference = reference or variant_names[0]
    if reference not in variant_names:
        print(f"기준 변형 `{reference}`가 실행할 변형에 없습니다.")
        return EXIT_PRECONDITION
    library_id = await session.scalar(select(Library.id).where(Library.name == library_name))
    if library_id is None:
        print(
            f"실험 기관(`{library_name}`)이 없습니다. "
            "`uv run python scripts/seed_experiment.py`로 실험 장서를 넣으세요."
        )
        return EXIT_PRECONDITION
    splits = [name for name in SPLIT_NAMES if split in ("all", name)]
    queries = [q for q in queries if q.split in splits]

    key_ids = await library_keys(session, library_id)
    id_keys = {book_id: key for key, book_id in key_ids.items()}
    recommendable = set(await session.scalars(recommendable_ids(library_id)))
    children = set(await session.scalars(children_book_ids(library_id)))
    missing = sorted(labels.book_keys() - key_ids.keys())

    scores: dict[str, dict[str, QueryScore]] = {}
    results: dict[str, dict[str, list[dict]]] = {}
    elapsed: dict[str, list[float]] = {}
    violations = {"추천할 수 없는 책": 0, "어린이 요청의 일반 도서": 0}
    for name in variant_names:
        scores[name], results[name], elapsed[name] = {}, {}, []
        for query in queries:
            within = children_book_ids(library_id) if query.children else None
            started = time.perf_counter()
            ranked = await run_variant(session, embedder, variants[name], library_id, query, within)
            elapsed[name].append((time.perf_counter() - started) * 1000)
            ids = [item.library_book_id for item in ranked]
            violations["추천할 수 없는 책"] += sum(1 for i in ids if i not in recommendable)
            if query.children:
                violations["어린이 요청의 일반 도서"] += sum(1 for i in ids if i not in children)
            groups = await _groups(session, library_id, ids)
            keys = [id_keys.get(i, f"id:{i}") for i in ids]
            grades = labels.grades(query.id)
            scores[name][query.id] = score_query(
                keys, grades, {id_keys.get(i, f"id:{i}"): groups[i] for i in ids if i in groups}
            )
            results[name][query.id] = [
                {
                    "key": key,
                    "score": item.score,
                    "ranks": dict(item.ranks),
                    "series_hidden": item.series_hidden,
                    "grade": grades.get(key),
                }
                for key, item in zip(keys, ranked, strict=True)
            ]

    stages = labels.stage_counts()
    by = labels.by_counts()
    lines = [
        "# 추천 실험: 주제로 찾기",
        "",
        f"시각: {datetime.now():%Y-%m-%d %H:%M:%S}",
        "LLM·외부 API 호출 없음. 장서는 YES24 스테디셀러, 기관은 가상이다. "
        "수치를 실제 서비스 성능으로 쓰지 않는다.",
        "",
        "## 지문",
        "",
        *fingerprint,
        f"- 실험 기관: {library_name}",
        f"- 추천 가능한 책 {len(recommendable)}권, 어린이 도서 {len(children & recommendable)}권",
        *[f"- 벡터 {line}" for line in await _vector_counts(session, library_id)],
        f"- 질의 {len(queries)}개 ({', '.join(SPLIT_NAMES[s] for s in splits)})",
        f"- 라벨: 실행 전 {stages.get('before', 0)}건, 실행 뒤 보충 {stages.get('pool', 0)}건,"
        f" 찾지 못한 키 {len(missing)}건",
        f"- 라벨을 단 쪽: claude {by.get('claude', 0)}건(초안),"
        f" user {by.get('user', 0)}건(사람이 확인·고침)",
    ]
    if fields is not None:
        held_out = sum(1 for key in labels.book_keys() if fields.get(key) in HOLDOUT_FIELDS)
        lines.append(f"- 남겨 둔 분야의 책에 달린 라벨 {held_out}건(후보로만 남는다)")
    lines += [f"- 기준 변형: `{reference}`", "", "## 변형", ""]
    lines += [_settings_line(variants[name]) for name in variant_names]
    lines += ["", "## 규칙 위반", ""]
    lines += [f"- {kind}: {count}건" for kind, count in violations.items()]
    for name in splits:
        part = [q for q in queries if q.split == name]
        if not part:
            continue
        lines += ["", f"## {SPLIT_NAMES[name]} 세트 ({len(part)}개)", ""]
        lines += _table(variant_names, scores, part, reference)
        for label, belongs in GROUPS:
            group = [q for q in part if belongs(q)]
            if group:
                lines += ["", f"### {SPLIT_NAMES[name]} · {label} ({len(group)}개)", ""]
                lines += _table(variant_names, scores, group, reference)
    lines += ["", "## 걸린 시간", ""]
    lines += [
        f"걸린 시간 `{name}`: 질의당 평균 {mean(times):.0f}ms, 최대 {max(times, default=0):.0f}ms"
        for name, times in elapsed.items()
    ]
    summary = "\n".join(lines) + "\n"
    await asyncio.to_thread(_write, out, summary, results)
    print(summary)
    print(f"결과: {out}")
    return EXIT_PRECONDITION if any(violations.values()) else EXIT_OK


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    try:
        queries = load_topic(TOPIC_FILE)
    except (OSError, SetError) as exc:
        print(f"평가 세트를 읽을 수 없습니다: {exc}", file=sys.stderr)
        return EXIT_PRECONDITION
    path = labels_file("topic")
    if not path.exists():
        print(
            f"라벨 파일이 없습니다: {path}\n실행 전 라벨을 먼저 답니다: "
            "`uv run python -m evals.recommendation.label topic`",
            file=sys.stderr,
        )
        return EXIT_PRECONDITION
    try:
        fields = load_fields(COLLECTION_FILE)
    except CollectionMissingError:
        fields = None
    fingerprint = [
        f"- 평가 세트 해시: {file_hash(TOPIC_FILE)}",
        f"- 라벨 해시: {file_hash(path)}",
        f"- 커밋: {git_state()}",
    ]
    names = [name for name in args.variants.split(",") if name] or list(DEFAULT_VARIANTS)
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with (
            AsyncSession(engine, expire_on_commit=False) as session,
            httpx.AsyncClient(
                base_url=settings.embedding_base_url, timeout=settings.embedding_timeout_seconds
            ) as http,
        ):
            return await run_topic(
                session,
                CachedEmbedder(TeiEmbedder(http, settings)),
                queries=queries,
                labels=Labels(path),
                out=RUNS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}",
                variant_names=names,
                split=args.split,
                reference=args.reference,
                fingerprint=fingerprint,
                fields=fields,
            )
    except EmbeddingError as exc:
        print(
            f"중단: 질의를 인코딩할 수 없습니다 ({exc}). 캐시에 없는 질의가 있습니다. "
            "`docker compose --profile embedding up -d embedder`로 임베딩 서버를 켜세요.",
            file=sys.stderr,
        )
        return EXIT_STOPPED
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.recommendation")
    parser.add_argument("set", choices=["topic"], help="요청 종류 (지금은 주제로 찾기만)")
    parser.add_argument("--variants", default="", help=f"변형 이름(쉼표로). {', '.join(VARIANTS)}")
    parser.add_argument("--split", choices=["tune", "check", "all"], default="tune")
    parser.add_argument("--reference", help="짝 비교의 기준 변형(없으면 첫 변형)")
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
