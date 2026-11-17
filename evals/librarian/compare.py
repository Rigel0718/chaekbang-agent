"""AI 사서 평가 실행 여러 개를 시나리오별로 나란히 본다(add-topic-search-tool 결정 11). LLM 없음.

    uv run python -m evals.librarian.compare <실행> <실행> ... [--out 파일]

실행은 `data/runs/` 아래 폴더 이름이나 경로다. 저장된 시나리오 기록(`NN-<id>.json`)만 읽는다.
시나리오마다 실행별로 기대 일치, 규칙 위반 수, 어린이 판단(기대와 같은지), 주제 낱말 일치, 검색 tool
호출 수, 걸린 시간(단계 시간 합), 토큰을 낸다. 끝에 실행별 합계가 있다. 주제 낱말 일치를 기록하기
전의 실행은 그 칸이 `-`다.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from evals.librarian.catalog import DATA_FILE

RUNS_DIR = DATA_FILE.parent / "runs"
SEARCH_TOOLS = ("search_collection", "search_children_books")


@dataclass(frozen=True)
class Row:
    scenario: str
    met: bool
    violations: int
    children_ok: bool
    topic_met: bool | None
    searches: int
    seconds: float
    tokens: tuple[int, int]


def _row(record: dict) -> Row:
    turns = record["turns"]
    return Row(
        scenario=record["id"],
        met=record["expectation_met"],
        violations=sum(len(v) for v in record["violations"].values()),
        children_ok=record["children_judged"] == record["expected_children"],
        topic_met=record.get("topic_met"),
        searches=sum(t in SEARCH_TOOLS for turn in turns for t in turn["tools"]),
        seconds=sum(s["duration_ms"] or 0 for turn in turns for s in turn["steps"]) / 1000,
        tokens=(
            sum(turn["input_tokens"] for turn in turns),
            sum(turn["output_tokens"] for turn in turns),
        ),
    )


def load_run(path: Path) -> dict[str, Row]:
    rows = [
        _row(json.loads(p.read_text(encoding="utf-8"))) for p in sorted(path.glob("[0-9]*-*.json"))
    ]
    return {row.scenario: row for row in rows}


def _resolve(name: str) -> Path:
    path = Path(name)
    return path if path.exists() else RUNS_DIR / name


def _cell(row: Row | None) -> str:
    if row is None:
        return "없음"
    topic = "-" if row.topic_met is None else ("주제○" if row.topic_met else "주제×")
    return (
        f"{'○' if row.met else '×'} 위반{row.violations} "
        f"{'어린이○' if row.children_ok else '어린이×'} {topic} "
        f"검색{row.searches} {row.seconds:.1f}s"
    )


def report(names: Sequence[str], runs: Sequence[dict[str, Row]]) -> str:
    scenarios = list(dict.fromkeys(s for run in runs for s in run))
    lines = [
        "# AI 사서 평가 비교",
        "",
        "칸: 기대(○×) 위반 수, 어린이 판단이 기대와 같은지, 주제 낱말 일치, 검색 tool 호출 수, "
        "단계 시간 합",
        "",
        "| 시나리오 | " + " | ".join(names) + " |",
        "|" + " --- |" * (len(names) + 1),
    ]
    for scenario in scenarios:
        cells = [_cell(run.get(scenario)) for run in runs]
        lines.append(f"| {scenario} | " + " | ".join(cells) + " |")
    lines += ["", "| 합계 | " + " | ".join(names) + " |", "|" + " --- |" * (len(names) + 1)]
    totals = {
        "시나리오": lambda r: str(len(r)),
        "기대 불일치": lambda r: str(sum(not x.met for x in r.values())),
        "규칙 위반": lambda r: str(sum(x.violations for x in r.values())),
        "어린이 판단 불일치": lambda r: str(sum(not x.children_ok for x in r.values())),
        "주제 낱말 일치": lambda r: (
            f"{sum(bool(x.topic_met) for x in r.values())}"
            f"/{sum(x.topic_met is not None for x in r.values())}"
        ),
        "검색 tool 호출": lambda r: str(sum(x.searches for x in r.values())),
        "단계 시간 합(초)": lambda r: f"{sum(x.seconds for x in r.values()):.1f}",
        "토큰 입력/출력": lambda r: (
            f"{sum(x.tokens[0] for x in r.values())}/{sum(x.tokens[1] for x in r.values())}"
        ),
    }
    for label, value in totals.items():
        lines.append(f"| {label} | " + " | ".join(value(run) for run in runs) + " |")
    missed = {
        name: [s for s, row in run.items() if not row.met]
        for name, run in zip(names, runs, strict=True)
    }
    lines += [
        "",
        *(f"- {name} 기대 불일치: {', '.join(m) or '없음'}" for name, m in missed.items()),
    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.librarian.compare")
    parser.add_argument("runs", nargs="+", help="실행 폴더 이름(data/runs/ 아래) 또는 경로")
    parser.add_argument("--out", type=Path, help="표를 쓸 파일")
    args = parser.parse_args(argv)
    paths = [_resolve(name) for name in args.runs]
    missing = [str(p) for p in paths if not p.is_dir()]
    if missing:
        print(f"실행 폴더가 없습니다: {', '.join(missing)}", file=sys.stderr)
        return 1
    text = report([p.name for p in paths], [load_run(p) for p in paths])
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
