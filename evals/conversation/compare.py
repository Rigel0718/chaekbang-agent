"""대화 추천 평가 실행 사이 비교. LLM과 DB를 부르지 않는다.

    uv run python -m evals.conversation.compare <실행> <실행> [...]

저장된 실행(`items.json`)의 카드와 tool 결과 앞 5권을 **지금 라벨**로 다시 채점한다. 첫 실행을
기준으로 항목별 카드 nDCG@5 차이의 이김·비김·짐과 고정 시드 부트스트랩 95% 구간, 실행별 묶음
표를 낸다. 세트 해시가 다르면 멈춘다(종료 코드 1). 요약은 마지막 실행 폴더의
`compare-<기준>.md`에 쓴다.
"""

import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from evals.conversation.catalog import DATA_DIR
from evals.conversation.items import Group
from evals.conversation.score import ItemRun, group_rows, score_keys, table
from evals.recommendation.labels import Labels, labels_file
from evals.recommendation.metrics import compare

RUNS_DIR = DATA_DIR / "runs"
SETS = ("topic", "similar", "history")


@dataclass(frozen=True)
class SavedRun:
    name: str
    meta: dict
    items: list[ItemRun]


def load_run(path: Path) -> SavedRun:
    path = path if path.exists() else RUNS_DIR / path
    document = json.loads((path / "items.json").read_text(encoding="utf-8"))
    items = [ItemRun(**{**row, "group": Group(row["group"])}) for row in document["items"]]
    return SavedRun(path.name, document["meta"], items)


def current_labels() -> dict[str, dict[str, dict[str, int]]]:
    out = {}
    for name in SETS:
        labels = Labels(labels_file(name))
        out[name] = {item_id: labels.grades(item_id) for item_id in labels.items}
    return out


class SetMismatchError(ValueError):
    pass


def compare_runs(
    runs: Sequence[SavedRun], labels: Mapping[str, Mapping[str, Mapping[str, int]]]
) -> str:
    hashes = {json.dumps(r.meta["set_hashes"], sort_keys=True) for r in runs}
    if len(hashes) > 1:
        raise SetMismatchError(f"세트 해시가 다릅니다: {[r.meta['set_hashes'] for r in runs]}")
    base = runs[0]
    lines = [f"기준 `{base.name}`. 모든 실행을 지금 라벨로 다시 채점했다.", ""]
    lines += [
        "| 실행 | 모델 | 프로필 | 카드 nDCG@5 차이 | 이김·비김·짐 | 95% 구간 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]

    def ndcgs(run: SavedRun) -> dict[tuple[str, str], float]:
        return {
            (i.set_name, i.id): score_keys(i.cards, labels[i.set_name].get(i.id, {})).ndcg
            for i in run.items
        }

    reference = ndcgs(base)
    for run in runs:
        mine = ndcgs(run)
        shared = [k for k in reference if k in mine]
        if run is base:
            versus = "기준 | - | -"
        else:
            c = compare([reference[k] for k in shared], [mine[k] for k in shared])
            versus = (
                f"{c.mean_diff:+.3f} | {c.wins}·{c.ties}·{c.losses} | {c.low:+.3f} ~ {c.high:+.3f}"
            )
        lines.append(
            f"| {run.name} | {run.meta['model']} | {run.meta['profile_version']} | {versus} |"
        )
    for run in runs:
        lines += ["", f"### {run.name}", "", *table(group_rows(run.items, labels))]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str]) -> int:
    if len(argv) < 2:
        print("실행 폴더를 둘 이상 주세요.", file=sys.stderr)
        return 1
    runs = [load_run(Path(a)) for a in argv]
    try:
        text = compare_runs(runs, current_labels())
    except SetMismatchError as exc:
        print(exc, file=sys.stderr)
        return 1
    path = RUNS_DIR / runs[-1].name / f"compare-{runs[0].name}.md"
    path.write_text(text, encoding="utf-8")
    print(text)
    print(f"요약: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
