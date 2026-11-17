"""주제로 찾기에서 키워드 순위가 빈 질의 진단(add-topic-search-tool 결정 12). LLM·DB 없음.

    uv run python -m evals.recommendation.keyword_empty <주제 실행 폴더> [--variant hybrid-best]

실행 폴더(`data/runs/<시각>`, `topic` 세트)의 한 변형에서, 결과 상위 10권에 키워드 순위(`keyword`)가
하나도 없는 질의를 "키워드 순위가 빈 질의"로 본다. 합친 순위(RRF, 깊이 30)에서 키워드 1위 책의
점수는 적어도 `1 / (k + 1)`이라 벡터 순위만 있는 2위 이하보다 높으므로, 키워드 순위에 책이 있으면
상위 10권에 반드시 든다. 그래서 상위 10권만 보고 가를 수 있다.

두 묶음(키워드 순위 빔 / 있음)마다 질의 수, nDCG@5, 상위 5권의 라벨 0·1·2(라벨 없음) 건수를
조정·확인 세트별로 낸다. 함께 상위 5권의 책을 근거(키워드만 / 둘 다 / 벡터만)로 나눠 라벨 건수를
낸다. 결과는 실행 폴더의 `keyword-empty.md`다. 새 라벨을 달지 않는다.
"""

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from app.library.recommendation.topic import KEYWORD
from evals.recommendation.keys import DATA_DIR
from evals.recommendation.labels import Labels, labels_file
from evals.recommendation.metrics import DEEP, TOP, mean, ndcg
from evals.recommendation.sets import TopicQuery, load_topic

EMPTY = "키워드 순위 빔"
MATCHED = "키워드 순위 있음"


@dataclass(frozen=True)
class Group:
    split: str
    name: str  # EMPTY, MATCHED
    queries: tuple[str, ...]
    ndcg: float
    grades: Mapping[str, int]  # "0", "1", "2", "없음" → 상위 5권 건수


def keyword_empty(rows: Sequence[Mapping]) -> bool:
    return not any(KEYWORD in row.get("ranks", {}) for row in rows[:DEEP])


def groups(
    results: Mapping[str, Sequence[Mapping]], queries: Sequence[TopicQuery], labels: Labels
) -> list[Group]:
    out: list[Group] = []
    for split in ("tune", "check"):
        part = [q for q in queries if q.split == split and q.id in results]
        for name in (EMPTY, MATCHED):
            chosen = [q for q in part if keyword_empty(results[q.id]) == (name == EMPTY)]
            scores: list[float] = []
            counts = {"0": 0, "1": 0, "2": 0, "없음": 0}
            for query in chosen:
                rows = results[query.id]
                grades = [labels.grade(query.id, row["key"]) for row in rows]
                scores.append(ndcg(grades, list(labels.grades(query.id).values())))
                for grade in grades[:TOP]:
                    counts["없음" if grade is None else str(grade)] += 1
            out.append(Group(split, name, tuple(q.id for q in chosen), mean(scores), counts))
    return out


EVIDENCE = ("키워드만", "둘 다", "벡터만")


def evidence(row: Mapping) -> str:
    ranks = row.get("ranks", {})
    if KEYWORD in ranks:
        return EVIDENCE[1] if len(ranks) > 1 else EVIDENCE[0]
    return EVIDENCE[2]


def by_evidence(
    results: Mapping[str, Sequence[Mapping]], queries: Sequence[TopicQuery], labels: Labels
) -> dict[tuple[str, str], dict[str, int]]:
    """(세트, 근거) → 상위 5권의 라벨 건수."""
    out = {(s, e): {"0": 0, "1": 0, "2": 0, "없음": 0} for s in ("tune", "check") for e in EVIDENCE}
    for query in queries:
        for row in results.get(query.id, [])[:TOP]:
            grade = labels.grade(query.id, row["key"])
            out[(query.split, evidence(row))]["없음" if grade is None else str(grade)] += 1
    return out


def report(
    found: Sequence[Group],
    variant: str,
    books: Mapping[tuple[str, str], Mapping[str, int]] | None = None,
) -> str:
    lines = [
        "# 주제로 찾기: 키워드 순위가 빈 질의",
        "",
        f"변형 `{variant}`. 상위 5권의 라벨 건수. 라벨 없는 책은 nDCG에서 0이다.",
        "",
        "| 세트 | 묶음 | 질의 | nDCG@5 | 0 | 1 | 2 | 라벨 없음 | 질의 id |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    names = {"tune": "조정", "check": "확인"}
    for g in found:
        lines.append(
            f"| {names[g.split]} | {g.name} | {len(g.queries)} | {g.ndcg:.3f} | "
            f"{g.grades['0']} | {g.grades['1']} | {g.grades['2']} | {g.grades['없음']} | "
            f"{', '.join(g.queries) or '-'} |"
        )
    if books:
        lines += [
            "",
            "상위 5권의 책을 근거로 나눈 라벨 건수",
            "",
            "| 세트 | 근거 | 책 | 0 | 1 | 2 | 라벨 없음 | 2의 비율 |",
            "| --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for (split, kind), c in books.items():
            total = sum(c.values())
            share = f"{c['2'] / total:.0%}" if total else "-"
            lines.append(
                f"| {names[split]} | {kind} | {total} | {c['0']} | {c['1']} | {c['2']} | "
                f"{c['없음']} | {share} |"
            )
    return "\n".join(lines) + "\n"


def run(path: Path, variant: str) -> str:
    results = json.loads((path / "results.json").read_text(encoding="utf-8"))[variant]
    queries, labels = load_topic(), Labels(labels_file("topic"))
    text = report(groups(results, queries, labels), variant, by_evidence(results, queries, labels))
    (path / "keyword-empty.md").write_text(text, encoding="utf-8")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.recommendation.keyword_empty")
    parser.add_argument("run", type=Path, help="주제 실행 폴더(data/runs/<시각>)")
    parser.add_argument("--variant", default="hybrid-best")
    args = parser.parse_args()
    path = args.run if args.run.exists() else DATA_DIR / "runs" / args.run
    if not (path / "results.json").exists():
        print(f"실행 결과가 없습니다: {path}", file=sys.stderr)
        return 1
    print(run(path, args.variant))
    return 0


if __name__ == "__main__":
    sys.exit(main())
