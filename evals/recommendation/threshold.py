"""비슷한 책의 최소 유사도 진단(add-related-books 결정 10). LLM과 외부 API를 부르지 않는다.

    uv run python -m evals.recommendation.threshold <비슷한 책 실행 폴더> [--variant sim-rrf]

실행 폴더(`data/runs/<시각>`, `similar` 세트)의 한 변형에서 상위 10권 중 **근거가 벡터 이웃
하나뿐인 책**만 모은다. 기준 책의 저장된 벡터와의 코사인을 개발 DB에서 읽고, 지금 라벨(0·1·2)별로
센다. 새 라벨을 달지 않는다. 라벨 없는 책은 세지 않는다.

규칙(`choose_threshold`): 0.30~0.80을 0.01 간격으로 보며, 조정 세트에서 벡터 근거만 있는 0 라벨을
절반 이상 빼고 2 라벨은 5% 이하만 빼는 가장 큰 문턱을 고른다. 확인 세트에서도 0 라벨을 2 라벨보다
많이(비율로) 빼야 한다. 넘는 문턱이 없으면 문턱 없음이다.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.library.models.library import Library
from app.library.recommendation.related import VECTOR, vector_similarities
from app.seed.experiment import LIBRARY_NAME
from evals.collection.fetch import DATA_FILE as COLLECTION_FILE
from evals.recommendation.keys import DATA_DIR, library_keys, load_fields
from evals.recommendation.sets import load_seeds

TOP = 10
GRID = tuple(round(0.30 + step / 100, 2) for step in range(51))  # 0.30 ~ 0.80
MIN_ZERO_REMOVED = 0.5
MAX_TWO_REMOVED = 0.05


@dataclass(frozen=True)
class Point:
    split: str  # tune, check
    item: str  # 기준 책 항목 id
    key: str  # 결과 책 키
    cosine: float
    grade: int


@dataclass(frozen=True)
class Cut:
    threshold: float
    zero_removed: float  # 0 라벨 중 뺀 비율
    two_removed: float  # 2 라벨 중 뺀 비율
    one_removed: float


def cut_at(points: Sequence[Point], threshold: float) -> Cut:
    def removed(grade: int) -> float:
        graded = [p for p in points if p.grade == grade]
        if not graded:
            return 0.0
        return sum(p.cosine < threshold for p in graded) / len(graded)

    return Cut(threshold, removed(0), removed(2), removed(1))


def choose_threshold(
    tune: Sequence[Point], check: Sequence[Point], grid: Sequence[float] = GRID
) -> float | None:
    """규칙을 넘는 가장 큰 문턱. 없으면 None. 조정 세트에 0 라벨이 없으면 None이다."""
    if not any(p.grade == 0 for p in tune):
        return None
    passing = [
        t
        for t in grid
        if (c := cut_at(tune, t)).zero_removed >= MIN_ZERO_REMOVED
        and c.two_removed <= MAX_TWO_REMOVED
    ]
    for threshold in sorted(passing, reverse=True):
        confirm = cut_at(check, threshold)
        if confirm.zero_removed > confirm.two_removed:
            return threshold
    return None


async def collect(run: Path, variant: str) -> list[Point]:
    results = json.loads((run / "results.json").read_text(encoding="utf-8"))[variant]
    seeds, _ = load_seeds(load_fields(COLLECTION_FILE))
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    points: list[Point] = []
    try:
        async with engine.connect() as conn, AsyncSession(bind=conn) as session:
            library_id = await session.scalar(
                select(Library.id).where(Library.name == LIBRARY_NAME)
            )
            if library_id is None:
                raise SystemExit("실험 기관이 없습니다. `uv run python scripts/seed_experiment.py`")
            ids = await library_keys(session, library_id)
            for seed in seeds:
                rows = [
                    r
                    for r in results.get(seed.id, [])[:TOP]
                    if set(r["ranks"]) == {VECTOR} and r.get("grade") is not None
                ]
                found = await vector_similarities(
                    session,
                    settings.embedding_model,
                    library_id,
                    ids[seed.book],
                    [ids[r["key"]] for r in rows],
                )
                points += [
                    Point(seed.split, seed.id, r["key"], found[ids[r["key"]]], r["grade"])
                    for r in rows
                    if ids[r["key"]] in found
                ]
    finally:
        await engine.dispose()
    return points


def report(points: Sequence[Point]) -> str:
    tune = [p for p in points if p.split == "tune"]
    check = [p for p in points if p.split == "check"]
    lines = ["# 비슷한 책 최소 유사도 진단", ""]
    for name, part in (("조정", tune), ("확인", check)):
        counts = {g: sum(p.grade == g for p in part) for g in (0, 1, 2)}
        lines.append(
            f"- {name}: 벡터 근거만 있는 책 {len(part)}건 "
            f"(0: {counts[0]}, 1: {counts[1]}, 2: {counts[2]})"
        )
        for grade in (0, 1, 2):
            values = sorted(p.cosine for p in part if p.grade == grade)
            if values:
                lines.append(
                    f"  - 라벨 {grade}: 코사인 {values[0]:.3f} ~ {values[-1]:.3f}, "
                    f"가운데 {values[len(values) // 2]:.3f}"
                )
    lines += [
        "",
        "| 문턱 | 조정 0 뺌 | 조정 1 뺌 | 조정 2 뺌 | 확인 0 뺌 | 확인 2 뺌 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for t in GRID[::5]:
        a, b = cut_at(tune, t), cut_at(check, t)
        lines.append(
            f"| {t:.2f} | {a.zero_removed:.0%} | {a.one_removed:.0%} | {a.two_removed:.0%} | "
            f"{b.zero_removed:.0%} | {b.two_removed:.0%} |"
        )
    chosen = choose_threshold(tune, check)
    lines += ["", f"결론: {'문턱 없음' if chosen is None else f'문턱 {chosen:.2f}'}"]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.recommendation.threshold")
    parser.add_argument("run", type=Path, help="비슷한 책 실행 폴더(data/runs/<시각>)")
    parser.add_argument("--variant", default="sim-rrf")
    args = parser.parse_args()
    run = args.run if args.run.exists() else DATA_DIR / "runs" / args.run
    if not (run / "results.json").exists():
        print(f"실행 결과가 없습니다: {run}", file=sys.stderr)
        return 1
    text = report(asyncio.run(collect(run, args.variant)))
    (run / "threshold.md").write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
