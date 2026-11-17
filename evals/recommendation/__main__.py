"""추천 실험 실행. LLM과 외부 API를 부르지 않는다.

    uv run python -m evals.recommendation topic|similar|history [--variants a,b,…]
                                                [--split tune|check|all] [--reference <변형>]
                                                [--holdout] [--loan-signals <파일>]

개발 DB(`DATABASE_URL`)의 실험 기관(`실험용 가상 작은도서관`, 이름으로 찾는다)에서 읽기만 한다.
같은 평가 세트(`sets/topic.json`, `data/seeds.json`)와 라벨(`data/labels/<세트>.json`)로 변형을
나란히 잰다. 변형 표는 세트마다 따로다(`variants.py`).

- 주제로 찾기는 질의 인코딩만 로컬 임베딩 서버를 쓴다. 질의 벡터는 `data/query_vectors.json`에
  캐시해, 캐시가 다 차 있으면 서버 없이 돈다. 비슷한 책과 최근 기록은 저장된 벡터만 써서 임베딩
  서버가 필요 없다.
- 어린이 요청과 어린이 기준 책(최근 기록이면 기록의 책이 모두 어린이 도서)에는 어린이 도서 조건을
  코드가 넘긴다. 결과에 추천할 수 없는 책이나 어린이 항목의 일반 도서가 있으면 위반으로 세고
  종료 코드가 1이다.
- 결과는 `data/runs/<시각>/`에 쓴다(`summary.md`, `results.json`). 책 키가 실험 장서를 가리켜
  저장소에서 뺀 폴더다. 같은 데이터에서 같은 명령은 시각과 걸린 시간 줄만 빼고 요약이 같다.
- 함께 대출·마니아·다독자를 쓰는 변형만 정보나루 대출 신호 파일(`evals/collection/loans.py`가 받은
  것)을 읽는다. 파일이 없으면 받기 명령을 알리고 종료 코드 1이다.
- `--holdout`은 남겨 둔 분야 세트(`sets/topic-holdout.json`, `data/seeds-holdout.json`, 라벨
  `data/labels/holdout-<세트>.json`)를 정해 둔 변형으로만 돈다(`variants.HOLDOUT_VARIANTS`).
- 장서는 YES24 스테디셀러이고 기관은 가상이다. 수치를 실제 서비스 성능으로 쓰지 않는다.

종료 코드: 0 완료, 1 전제 조건·인자 문제나 규칙 위반, 2 임베딩 서버 장애.
"""

import argparse
import asyncio
import json
import subprocess
import sys
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.central.embedding import Embedder, EmbeddingError, EmbeddingFailure
from app.central.external.data4library.definitions import AGE_CHILDREN
from app.central.external.tei import TeiEmbedder
from app.central.models import Book, OfficialBookEmbedding
from app.core.config import get_settings
from app.features.children.service import children_book_ids
from app.library.models.catalog import LibraryBook
from app.library.models.embedding import BookEmbedding
from app.library.models.library import Library
from app.library.recommendation.authors import writer_keys_sql
from app.library.recommendation.related import (
    AUTHOR,
    CO_LOAN,
    KDC,
    MANIA,
    POPULAR_ALL,
    READER,
    SERIES,
    VECTOR,
    SimilarSettings,
    held_ranking,
    history_co_loan_ranking,
    kdc_ranking,
    national_popular_ranking,
    popular_ranking,
    similar_rankings,
)
from app.library.recommendation.search import recommendable_ids
from app.seed.experiment import LIBRARY_NAME, CollectionMissingError
from evals.collection.fetch import DATA_FILE as COLLECTION_FILE
from evals.collection.loans import LOANS_FILE
from evals.recommendation.cache import CachedEmbedder
from evals.recommendation.keys import DATA_DIR, HOLDOUT_FIELDS, library_keys, load_fields
from evals.recommendation.labels import Labels, labels_file
from evals.recommendation.llm_keywords import keywords_line, with_llm_keywords
from evals.recommendation.metrics import QueryScore, compare, mean, score_query
from evals.recommendation.sample import SAMPLE_SIZES, sample_line
from evals.recommendation.sets import (
    HOLDOUT_SEEDS_FILE,
    HOLDOUT_TOPIC_FILE,
    SEEDS_FILE,
    TOPIC_FILE,
    History,
    Seed,
    SetError,
    TopicQuery,
    file_hash,
    load_seeds,
    load_topic,
)
from evals.recommendation.signals import (
    FETCH_COMMAND,
    FileLoanSignals,
    LoanSignalsMissingError,
)
from evals.recommendation.variants import (
    DEFAULT_SETS,
    DEFAULT_VARIANTS,
    HISTORY_VARIANTS,
    HOLDOUT_VARIANTS,
    SIMILAR_VARIANTS,
    VARIANT_SETS,
    VARIANTS,
    Variant,
    needs_loans,
    run_variant,
)

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


async def _source_counts(session: AsyncSession, library_id: int) -> str:
    """실험 기관이 소장한 공식 서지의 출처(서명·저자의 출처)별 수. 장서 상태를 가리는 지문이다."""
    rows = await session.execute(
        select(Book.external_source, func.count(func.distinct(Book.id)))
        .join(LibraryBook, LibraryBook.book_id == Book.id)
        .where(LibraryBook.library_id == library_id)
        .group_by(Book.external_source)
        .order_by(Book.external_source)
    )
    return ", ".join(f"{source or '없음'} {count}" for source, count in rows) or "없음"


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


def _plain(value):
    """설정 값을 JSON으로 쓸 수 있게: 열거형 키와 값은 이름으로, 튜플은 목록으로."""
    if isinstance(value, Mapping):
        return {str(getattr(k, "value", k)): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return getattr(value, "value", value)


def _settings_line(variant: Variant) -> str:
    if variant.settings is None:
        return f"- `{variant.name}`: {variant.note}"
    values = _plain(asdict(variant.settings))
    values.pop("limit")
    return f"- `{variant.name}`: {variant.note} — {json.dumps(values, ensure_ascii=False)}"


def _table(
    names: Sequence[str],
    scores: Mapping[str, Mapping[str, QueryScore]],
    queries: Sequence[Any],
    reference: str,
    unit: str = "질의",
) -> list[str]:
    lines = [
        f"| 변형 | {unit} | nDCG@5 | Hit@5 | Recall@10 | 겹침 | 라벨 없음 "
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


@dataclass(frozen=True)
class BaseItem:
    """비슷한 책의 기준 책 하나, 또는 최근 기록 하나. 실행할 때 책 키를 기관 도서 id로 바꾼 것."""

    id: str
    split: str
    base_ids: tuple[int, ...]
    children: bool  # 기준 책이 모두 어린이 도서다(어린이 도서 조건을 건다)
    group: str  # 비슷한 책: related / alone, 최근 기록: same / mixed / children


@dataclass(frozen=True)
class SetSpec:
    """세트마다 다른 것: 제목, 변형 표, 묶음, 항목과 신호 건수를 만드는 함수."""

    title: str
    variants: Mapping[str, Variant]
    groups: Sequence[tuple[str, Callable[[Any], bool]]]
    unit: str = "질의"
    sample_size: int = 0  # 고정 표본 검수의 표본 수. 0이면 요약에 적지 않는다
    # (session, library_id, 책 키 → id, 어린이 도서 id) → 항목. None이면 넘겨받은 항목 그대로다
    resolve: Callable[..., Awaitable[Sequence[Any]]] | None = None
    # (session, embedder, library_id, 항목, loan_signals) → 요약에 넣을 신호 건수 줄
    signal_lines: Callable[..., Awaitable[list[str]]] | None = None


TOPIC_SPEC = SetSpec("주제로 찾기", VARIANTS, GROUPS)


async def _related_flags(session: AsyncSession, library_id: int) -> dict[int, bool]:
    """추천 가능한 책마다 같은 지은이·시리즈의 다른 책이 장서에 있는지(`pick`과 같은 정의)."""
    rows = await session.execute(
        select(LibraryBook.id, writer_keys_sql(), Book.series_keys)
        .outerjoin(Book, Book.id == LibraryBook.book_id)
        .where(
            LibraryBook.library_id == library_id,
            LibraryBook.id.in_(recommendable_ids(library_id)),
        )
    )
    names = {
        i: {*(authors or []), *(f"s:{k}" for k in series or [])} for i, authors, series in rows
    }
    counts: dict[str, int] = {}
    for group in names.values():
        for name in group:
            counts[name] = counts.get(name, 0) + 1
    return {i: any(counts[name] > 1 for name in group) for i, group in names.items()}


def _ids(item_id: str, keys: Sequence[str], key_ids: Mapping[str, int]) -> tuple[int, ...]:
    missing = [key for key in keys if key not in key_ids]
    if missing:
        raise SetError(item_id, f"실험 기관에 없는 책 {missing}")
    return tuple(key_ids[key] for key in keys)


def similar_spec(seeds: Sequence[Seed]) -> SetSpec:
    async def resolve(session, library_id, key_ids, children) -> list[BaseItem]:
        related = await _related_flags(session, library_id)
        items = []
        for seed in seeds:
            (base,) = _ids(seed.id, [seed.book], key_ids)
            group = "related" if related.get(base) else "alone"
            items.append(BaseItem(seed.id, seed.split, (base,), base in children, group))
        return items

    async def signal_lines(session, embedder, library_id, items, loan_signals=None) -> list[str]:
        names = (SERIES, AUTHOR, KDC, VECTOR, *((CO_LOAN, MANIA, READER) if loan_signals else ()))
        sizes: dict[str, list[int]] = {name: [] for name in names}
        levels: dict[str, list[int]] = {"three": [], "nested": []}
        settings = SimilarSettings(signals=dict.fromkeys(names, 1.0))
        for item in items:
            within = children_book_ids(library_id) if item.children else None
            rankings = await similar_rankings(
                session,
                embedder.name,
                library_id=library_id,
                library_book_id=item.base_ids[0],
                within=within,
                settings=settings,
                loan_signals=loan_signals,
            )
            for name, ranking in rankings.items():
                sizes[name].append(len(ranking))
            for level, counts in levels.items():
                found = await kdc_ranking(
                    session, library_id, item.base_ids[0], within=within, level=level
                )
                counts.append(len(found))
        lines = [_signal_line(SIGNAL_NAMES[name], counts) for name, counts in sizes.items()]
        lines += [_signal_line(SIGNAL_NAMES[f"kdc-{lv}"], counts) for lv, counts in levels.items()]
        if loan_signals is not None:
            lines += await _loan_lines(session, library_id, items, loan_signals)
        return lines

    groups = (
        ("어린이", lambda i: i.children),
        ("일반", lambda i: not i.children),
        ("관련 책 있음", lambda i: i.group == "related"),
        ("관련 책 없음", lambda i: i.group == "alone"),
    )
    return SetSpec(
        "비슷한 책",
        SIMILAR_VARIANTS,
        groups,
        "기준 책",
        SAMPLE_SIZES["similar"],
        resolve,
        signal_lines,
    )


def history_spec(histories: Sequence[History], fields: Mapping[str, str]) -> SetSpec:
    async def resolve(session, library_id, key_ids, children) -> list[BaseItem]:
        items = []
        for history in histories:
            bases = _ids(history.id, history.books, key_ids)
            all_children = all(base in children for base in bases)
            same = len({fields.get(key) for key in history.books}) == 1
            group = "children" if all_children else "same" if same else "mixed"
            items.append(BaseItem(history.id, history.split, bases, all_children, group))
        return items

    async def signal_lines(session, embedder, library_id, items, loan_signals=None) -> list[str]:
        sizes: dict[str, list[int]] = {name: [] for name in (SERIES, AUTHOR, KDC, VECTOR)}
        popular = []
        co_loans: list[int] = []
        national: list[int] = []
        for item in items:
            within = children_book_ids(library_id) if item.children else None
            merged: dict[str, set[int]] = {name: set() for name in sizes}
            for base in item.base_ids:
                rankings = await similar_rankings(
                    session,
                    embedder.name,
                    library_id=library_id,
                    library_book_id=base,
                    within=within,
                    exclude=item.base_ids,
                )
                for name, ranking in rankings.items():
                    merged[name].update(ranking)
            for name, found in merged.items():
                sizes[name].append(len(found))
            popular.append(len(await popular_ranking(session, library_id, within=within)))
            if loan_signals is not None:
                found = await history_co_loan_ranking(
                    session, library_id, item.base_ids, loan_signals, within=within
                )
                co_loans.append(len(found))
                group = AGE_CHILDREN.key if item.children else POPULAR_ALL
                found = await national_popular_ranking(
                    session, library_id, loan_signals, age_group=group, within=within
                )
                national.append(len(found))
        lines = [_signal_line(SIGNAL_NAMES[name], counts) for name, counts in sizes.items()]
        lines.append(_signal_line("우리 도서관 인기", popular))
        if loan_signals is not None:
            lines.append(_signal_line(SIGNAL_NAMES[CO_LOAN], co_loans))
            lines.append(_signal_line("정보나루 인기(채우기 깊이 30)", national))
            lines += await _loan_lines(session, library_id, items, loan_signals)
        return lines

    groups = (
        ("같은 분야", lambda i: i.group == "same"),
        ("섞인 분야", lambda i: i.group == "mixed"),
        ("어린이", lambda i: i.group == "children"),
    )
    return SetSpec(
        "최근 기록",
        HISTORY_VARIANTS,
        groups,
        "기록",
        SAMPLE_SIZES["history"],
        resolve,
        signal_lines,
    )


SIGNAL_NAMES = {
    SERIES: "같은 시리즈",
    AUTHOR: "같은 저자",
    KDC: "같은 KDC 세목",
    "kdc-three": "같은 KDC 세 자리",
    "kdc-nested": "같은 KDC 계층",
    VECTOR: "벡터 이웃",
    CO_LOAN: "함께 대출",
    MANIA: "마니아 추천(진단)",
    READER: "다독자 추천(진단)",
}


async def _isbns_of(session: AsyncSession, ids: Sequence[int]) -> dict[int, str]:
    """기관 도서 id → ISBN(공식 서지 먼저). ISBN 없는 책은 빠진다."""
    rows = await session.execute(
        select(LibraryBook.id, func.coalesce(Book.isbn, LibraryBook.isbn))
        .outerjoin(Book, Book.id == LibraryBook.book_id)
        .where(LibraryBook.id.in_(list(ids)))
    )
    return {book_id: isbn for book_id, isbn in rows if isbn}


async def _loan_lines(
    session: AsyncSession, library_id: int, items: Sequence[Any], loan_signals: FileLoanSignals
) -> list[str]:
    """대출 신호 파일의 순위 길이와, 그중 실험 기관이 가진 책·추천 가능한 책 수."""
    bases = sorted({base for item in items for base in item.base_ids})
    isbns = await _isbns_of(session, bases)
    lines = [f"- 대출 신호 파일: {loan_signals.fingerprint()}"]
    for kind in (CO_LOAN, MANIA, READER):
        length = held = usable = 0
        for base in bases:
            ranking = await loan_signals.co_loans(isbns[base], kind) if base in isbns else []
            length += len(ranking)
            held += len(await _held(session, library_id, ranking))
            usable += len(await held_ranking(session, library_id, ranking))
        lines.append(
            f"- {SIGNAL_NAMES[kind]} 순위: 길이 합 {length}, 실험 기관이 가진 책 {held}권,"
            f" 추천 가능 {usable}권 (기준 책 {len(bases)}권, ISBN 있음 {len(isbns)}권)"
        )
    for key, ranking in sorted(loan_signals.popular_conditions().items()):
        held = len(await _held(session, library_id, ranking))
        usable = len(await held_ranking(session, library_id, ranking, depth=len(ranking)))
        lines.append(
            f"- 정보나루 인기 `{key}`: 길이 {len(ranking)}, 가진 책 {held}권, 추천 가능 {usable}권"
        )
    return lines


async def _held(session: AsyncSession, library_id: int, isbns: Sequence[str]) -> set[str]:
    """그 기관이 가진(추천 가능 여부와 상관없이) ISBN."""
    if not isbns:
        return set()
    rows = await session.scalars(
        select(func.coalesce(Book.isbn, LibraryBook.isbn))
        .select_from(LibraryBook)
        .outerjoin(Book, Book.id == LibraryBook.book_id)
        .where(
            LibraryBook.library_id == library_id,
            func.coalesce(Book.isbn, LibraryBook.isbn).in_(list(isbns)),
        )
    )
    return set(rows)


def _signal_line(label: str, sizes: Sequence[int]) -> str:
    """신호 하나의 건수: 결과가 비지 않은 항목 수와, 그 항목들의 평균 권수."""
    filled = [size for size in sizes if size]
    average = f", 평균 {mean(filled):.1f}권" if filled else ""
    return f"- {label}: {len(filled)}건 (항목 {len(sizes)}개 중{average})"


async def run_topic(
    session: AsyncSession,
    embedder: Embedder,
    *,
    queries: Sequence[TopicQuery],
    variant_names: Sequence[str] = DEFAULT_VARIANTS,
    variants: Mapping[str, Variant] = VARIANTS,
    **options,
) -> int:
    """변형들을 주제 질의에 돌려 요약과 질의별 결과를 쓰고 종료 코드를 돌려준다."""
    return await run_set(
        session,
        embedder,
        spec=replace(TOPIC_SPEC, variants=variants),
        items=queries,
        variant_names=variant_names,
        **options,
    )


async def run_set(
    session: AsyncSession,
    embedder: Embedder,
    *,
    spec: SetSpec,
    labels: Labels,
    out: Path,
    variant_names: Sequence[str],
    items: Sequence[Any] = (),
    split: str = "all",
    reference: str | None = None,
    library_name: str = LIBRARY_NAME,
    fingerprint: Sequence[str] = (),
    fields: Mapping[str, str] | None = None,
    loan_signals: FileLoanSignals | None = None,
) -> int:
    """변형들을 한 세트에 돌려 요약과 항목별 결과를 쓰고 종료 코드를 돌려준다.

    대출 신호(loan_signals)는 그것을 쓰는 변형에만 넘긴다.
    """
    variants = spec.variants
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

    key_ids = await library_keys(session, library_id)
    id_keys = {book_id: key for key, book_id in key_ids.items()}
    recommendable = set(await session.scalars(recommendable_ids(library_id)))
    children = set(await session.scalars(children_book_ids(library_id)))
    missing = sorted(labels.book_keys() - key_ids.keys())
    if spec.resolve is not None:
        try:
            items = await spec.resolve(session, library_id, key_ids, children)
        except SetError as exc:
            print(f"평가 세트를 실험 기관에 맞출 수 없습니다: {exc}")
            return EXIT_PRECONDITION
    queries = [q for q in items if q.split in splits]
    child_label = "어린이 요청의 일반 도서" if spec.resolve is None else "어린이 항목의 일반 도서"

    scores: dict[str, dict[str, QueryScore]] = {}
    results: dict[str, dict[str, list[dict]]] = {}
    elapsed: dict[str, list[float]] = {}
    violations = {"추천할 수 없는 책": 0, child_label: 0}
    for name in variant_names:
        scores[name], results[name], elapsed[name] = {}, {}, []
        for query in queries:
            within = children_book_ids(library_id) if query.children else None
            started = time.perf_counter()
            uses = loan_signals if needs_loans(variants[name]) else None
            group = AGE_CHILDREN.key if query.children else POPULAR_ALL
            ranked = await run_variant(
                session, embedder, variants[name], library_id, query, within, uses, group
            )
            elapsed[name].append((time.perf_counter() - started) * 1000)
            ids = [item.library_book_id for item in ranked]
            violations["추천할 수 없는 책"] += sum(1 for i in ids if i not in recommendable)
            if query.children:
                violations[child_label] += sum(1 for i in ids if i not in children)
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
        f"# 추천 실험: {spec.title}",
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
        f"- 공식 서지 출처: {await _source_counts(session, library_id)}",
        *[f"- 벡터 {line}" for line in await _vector_counts(session, library_id)],
        f"- {spec.unit} {len(queries)}개 ({', '.join(SPLIT_NAMES[s] for s in splits)})",
        f"- 라벨: 실행 전 {stages.get('before', 0)}건, 실행 뒤 보충 {stages.get('pool', 0)}건,"
        f" 찾지 못한 키 {len(missing)}건",
        f"- 라벨을 단 쪽: claude {by.get('claude', 0)}건(초안),"
        f" user {by.get('user', 0)}건(사람이 확인·고침)",
    ]
    if spec.sample_size:
        lines.append(sample_line(labels, spec.sample_size))
    if fields is not None:
        held_out = sum(1 for key in labels.book_keys() if fields.get(key) in HOLDOUT_FIELDS)
        lines.append(f"- 남겨 둔 분야의 책에 달린 라벨 {held_out}건(후보로만 남는다)")
    if loan_signals is not None:
        lines.append(
            f"- 대출 신호: {loan_signals.fingerprint()}."
            f" 받지 않은 ISBN {loan_signals.pending_isbns()}건(그 책의 신호는 비어 있다)"
        )
    lines += [f"- 기준 변형: `{reference}`", "", "## 변형", ""]
    lines += [_settings_line(variants[name]) for name in variant_names]
    if spec.signal_lines is not None:
        lines += ["", "## 신호 건수", ""]
        lines += await spec.signal_lines(session, embedder, library_id, queries, loan_signals)
    lines += ["", "## 규칙 위반", ""]
    lines += [f"- {kind}: {count}건" for kind, count in violations.items()]
    for name in splits:
        part = [q for q in queries if q.split == name]
        if not part:
            continue
        lines += ["", f"## {SPLIT_NAMES[name]} 세트 ({len(part)}개)", ""]
        lines += _table(variant_names, scores, part, reference, spec.unit)
        for label, belongs in spec.groups:
            group = [q for q in part if belongs(q)]
            if group:
                lines += ["", f"### {SPLIT_NAMES[name]} · {label} ({len(group)}개)", ""]
                lines += _table(variant_names, scores, group, reference, spec.unit)
    lines += ["", "## 걸린 시간", ""]
    lines += [
        f"걸린 시간 `{name}`: {spec.unit}당 평균 {mean(times):.0f}ms,"
        f" 최대 {max(times, default=0):.0f}ms"
        for name, times in elapsed.items()
    ]
    summary = "\n".join(lines) + "\n"
    await asyncio.to_thread(_write, out, summary, results)
    print(summary)
    print(f"결과: {out}")
    return EXIT_PRECONDITION if any(violations.values()) else EXIT_OK


@dataclass(frozen=True)
class NamedModel:
    """저장된 벡터만 쓰는 실행의 인코더 자리. 모델 이름만 있고 인코딩은 할 수 없다."""

    name: str

    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        raise EmbeddingError(EmbeddingFailure.SERVER_ERROR, "이 실행은 질의를 인코딩하지 않는다")


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    holdout = bool(getattr(args, "holdout", False))
    path = labels_file(args.set, holdout)
    if not path.exists():
        flag = " --holdout" if holdout else ""
        print(
            f"라벨 파일이 없습니다: {path}\n실행 전 라벨을 먼저 답니다: "
            f"`uv run python -m evals.recommendation.draft dump {args.set}{flag}`",
            file=sys.stderr,
        )
        return EXIT_PRECONDITION
    try:
        fields = load_fields(COLLECTION_FILE)
    except CollectionMissingError:
        fields = None
    if args.set == "topic":
        set_file = HOLDOUT_TOPIC_FILE if holdout else TOPIC_FILE
    else:
        set_file = HOLDOUT_SEEDS_FILE if holdout else SEEDS_FILE
    try:
        if args.set == "topic":
            spec, items = TOPIC_SPEC, load_topic(set_file, holdout)
            if getattr(args, "keywords_from", None) is not None:
                items, skipped = with_llm_keywords(items, args.keywords_from)
        elif fields is None:
            print(
                "실험 장서 파일이 없습니다(기준 책의 분야를 읽는다). "
                "`uv run python -m evals.collection.fetch`",
                file=sys.stderr,
            )
            return EXIT_PRECONDITION
        else:
            seeds, histories = load_seeds(fields, set_file, holdout)
            spec = similar_spec(seeds) if args.set == "similar" else history_spec(histories, fields)
            items = ()
    except (OSError, SetError) as exc:
        print(f"평가 세트를 읽을 수 없습니다: {exc}", file=sys.stderr)
        return EXIT_PRECONDITION
    names = [name for name in args.variants.split(",") if name] or list(
        HOLDOUT_VARIANTS[args.set] if holdout else DEFAULT_SETS[args.set]
    )
    if holdout:
        allowed = HOLDOUT_VARIANTS[args.set]
        stray = [name for name in names if name not in allowed]
        if stray:
            print(
                f"남겨 둔 분야 세트에서 정해 두지 않은 변형: {', '.join(stray)}\n"
                f"쓸 수 있는 변형: {', '.join(allowed)}"
            )
            return EXIT_PRECONDITION
    loan_signals = None
    table = spec.variants
    if any(needs_loans(table[name]) for name in names if name in table):
        try:
            loan_signals = FileLoanSignals.load(args.loan_signals)
        except LoanSignalsMissingError as exc:
            print(f"{exc}\n대출 신호를 먼저 받습니다: `{FETCH_COMMAND}`", file=sys.stderr)
            return EXIT_PRECONDITION
    fingerprint = [
        f"- 평가 세트 해시: {file_hash(set_file)}" + (" (남겨 둔 분야 세트)" if holdout else ""),
        f"- 라벨 해시: {file_hash(path)}",
        f"- 커밋: {git_state()}",
    ]
    if args.set == "topic" and getattr(args, "keywords_from", None) is not None:
        fingerprint.append(keywords_line(args.keywords_from, skipped))
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with (
            AsyncSession(engine, expire_on_commit=False) as session,
            httpx.AsyncClient(
                base_url=settings.embedding_base_url, timeout=settings.embedding_timeout_seconds
            ) as http,
        ):
            embedder = (
                CachedEmbedder(TeiEmbedder(http, settings))
                if args.set == "topic"
                else NamedModel(settings.embedding_model)
            )
            return await run_set(
                session,
                embedder,
                spec=spec,
                items=items,
                labels=Labels(path),
                out=RUNS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}",
                variant_names=names,
                split=args.split,
                reference=args.reference,
                fingerprint=fingerprint,
                fields=fields,
                loan_signals=loan_signals,
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
    if sys.argv[1:2] == ["compare"]:
        from evals.recommendation.compare import main as compare_main  # noqa: PLC0415

        return compare_main(sys.argv[2:])
    parser = argparse.ArgumentParser(prog="python -m evals.recommendation")
    parser.add_argument("set", choices=list(VARIANT_SETS), help="요청 종류")
    names = "; ".join(f"{name}: {', '.join(table)}" for name, table in VARIANT_SETS.items())
    parser.add_argument("--variants", default="", help=f"변형 이름(쉼표로). {names}")
    parser.add_argument("--split", choices=["tune", "check", "all"], default="tune")
    parser.add_argument("--reference", help="짝 비교의 기준 변형(없으면 첫 변형)")
    parser.add_argument("--holdout", action="store_true", help="남겨 둔 분야 세트(정해 둔 변형만)")
    parser.add_argument(
        "--loan-signals", type=Path, default=LOANS_FILE, help="정보나루 대출 신호 파일"
    )
    parser.add_argument(
        "--keywords-from",
        type=Path,
        help="주제: 대화 추천 평가 실행의 실제 LLM 낱말(첫 검색)로 낱말을 바꾼다",
    )
    return asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
