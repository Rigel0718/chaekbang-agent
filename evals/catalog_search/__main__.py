"""서명·저자 찾기 평가. LLM과 외부 API를 부르지 않는다.

    uv run python -m evals.catalog_search [--fuzzy 0.7] [--found 0.85] [--sweep]

YES24 표본(`evals/librarian/data/`)을 테스트 DB(TEST_DATABASE_URL)의 트랜잭션 안에서 가상 기관에
적재해 돌리고 되돌린다. 개발 DB는 쓰지 않는다. 기준선은 지금의 키워드 검색(`search_collection`)이다.
결과는 `evals/catalog_search/data/runs/<시각>/`에 쓴다. 질의에 표본 서명이 들어 있어 저장소에서 뺀
폴더다. 기관과 사본 상태는 가상이므로 수치를 실제 서비스 성능으로 쓰지 않는다.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from alembic import command

from app.core.config import get_settings
from app.core.migrations import alembic_config
from app.library.recommendation import lookup
from app.library.recommendation.search import get_candidates, search_collection
from evals.catalog_search.metrics import Outcome, Score, misses, summarize
from evals.catalog_search.queries import SEARCH_KINDS, Book, Query, make_queries
from evals.librarian.__main__ import rollback_session
from evals.librarian.catalog import SampleMissingError, load_catalog, load_sample

RUNS_DIR = Path(__file__).parent / "data" / "runs"
HEADER = (
    "| 종류 | 질의 | 1위 | 5위 안 | MRR | 결과에 있음 | 결과 있음 "
    "| 기준선 1위 | 기준선 5위 안 | 기준선 MRR |"
)


async def _books(session, catalog) -> list[Book]:
    candidates = await get_candidates(session, catalog.library_id, sorted(catalog.recommendable))
    return [
        Book(i, c.library_book.shown("title"), c.library_book.shown("author"))
        for i, c in sorted(candidates.items())
    ]


async def _outcomes(session, library_id: int, queries: Sequence[Query]) -> tuple[list, list]:
    new, base = [], []
    for q in queries:
        if q.kind in SEARCH_KINDS:
            found = await lookup.find_books(session, library_id, q.text)
            ranked = tuple(f.candidate.library_book.id for f in found)
            old = await search_collection(session, library_id, [q.text])
            base.append(Outcome(q.kind, q.text, q.target, tuple(c.library_book.id for c in old)))
        elif q.kind == "suggest":
            ranked = tuple(
                s.library_book_id for s in await lookup.suggest_books(session, library_id, q.text)
            )
        else:  # found, unrelated
            ranked = tuple(
                c.library_book.id for c in await lookup.found_in_text(session, library_id, q.text)
            )
        new.append(Outcome(q.kind, q.text, q.target, ranked))
    return new, base


def _pct(value: float) -> str:
    return f"{value * 100:5.1f}%"


def _table(new: Sequence[Score], base: Sequence[Score]) -> list[str]:
    by_kind = {s.kind: s for s in base}
    lines = [HEADER, "|" + " --- |" * 10]
    for s in new:
        b = by_kind.get(s.kind)
        old = f"{_pct(b.hit1)} | {_pct(b.hit5)} | {b.mrr:.2f}" if b else "- | - | -"
        lines.append(
            f"| {s.kind} | {s.count} | {_pct(s.hit1)} | {_pct(s.hit5)} | {s.mrr:.2f} "
            f"| {_pct(s.found)} | {_pct(s.any_rate)} | {old} |"
        )
    return lines


async def evaluate(fuzzy: float, found: float, sweep: bool) -> int:
    settings = get_settings()
    if not settings.test_database_url:
        print("TEST_DATABASE_URL이 없습니다.", file=sys.stderr)
        return 1
    try:
        sample = load_sample()
    except SampleMissingError as exc:
        print(exc, file=sys.stderr)
        return 1
    await asyncio.to_thread(command.upgrade, alembic_config(settings.test_database_url), "head")
    out = RUNS_DIR / f"{datetime.now():%Y%m%d-%H%M%S}"
    out.mkdir(parents=True, exist_ok=True)
    lines = [
        f"표본: {len(sample.books)}권 (받은 날 {sample.fetched_on}). LLM·외부 API 호출 없음.",
        "기관과 사본 상태는 가상이다. 수치를 실제 서비스 성능으로 쓰지 않는다.",
    ]
    settings_list = (
        [(f, found) for f in (0.6, 0.65, 0.7, 0.75, 0.8)] + [(fuzzy, g) for g in (0.8, 0.85, 0.9)]
        if sweep
        else [(fuzzy, found)]
    )
    async with rollback_session(settings.test_database_url) as session:
        catalog = await load_catalog(session, sample)
        books = await _books(session, catalog)
        queries = make_queries(books)
        lines.append(f"찾을 수 있는 책 {len(books)}권, 질의 {len(queries)}개")
        for fuzzy_t, found_t in settings_list:
            lookup.FUZZY_THRESHOLD, lookup.FOUND_THRESHOLD = fuzzy_t, found_t
            new, base = await _outcomes(session, catalog.library_id, queries)
            lines += ["", f"### 오타 문턱 {fuzzy_t}, 찾은 책 문턱 {found_t}", ""]
            lines += _table(summarize(new), summarize(base))
            missed = [asdict(o) for o in misses(new, limit=0)]
            name = f"misses-{fuzzy_t}-{found_t}.json"
            (out / name).write_text(json.dumps(missed, ensure_ascii=False, indent=1), "utf-8")
    text = "\n".join(lines) + "\n"
    (out / "summary.md").write_text(text, encoding="utf-8")
    print(text)
    print(f"결과: {out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.catalog_search")
    parser.add_argument("--fuzzy", type=float, default=lookup.FUZZY_THRESHOLD, help="오타 문턱")
    parser.add_argument("--found", type=float, default=lookup.FOUND_THRESHOLD, help="찾은 책 문턱")
    parser.add_argument("--sweep", action="store_true", help="문턱을 바꿔 가며 표를 낸다")
    args = parser.parse_args()
    return asyncio.run(evaluate(args.fuzzy, args.found, args.sweep))


if __name__ == "__main__":
    sys.exit(main())
