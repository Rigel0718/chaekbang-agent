"""두 실행을 같은 세트·지금 라벨로 항목별 짝 비교한다.

uv run python -m evals.recommendation compare <기준 실행 폴더> <새 실행 폴더>

장서 값(공식 서지의 출처)을 바꾸기 전과 뒤처럼, 같은 세트를 다른 장서 상태에서 돌린 두 실행을
비교한다.
두 실행의 `results.json`에 남은 상위 10권 책 키를 **지금 라벨 파일 하나**로 다시 채점한다. 그래서
기준 실행 뒤에 단 보충 라벨이 두 실행에 똑같이 쓰인다. 변형마다 항목별 nDCG@5 차이로 이김·비김·짐과
고정 시드 부트스트랩 95% 구간을 낸다(`metrics.compare`, 차이는 새 − 기준).

- 조정·확인 세트를 따로 낸다. 주제 질의는 어린이·일반, 주제어·상황 묶음도 낸다. 비슷한 책·최근
  기록의 묶음(관련 책 있음, 분야 섞임)은 장서 상태에 따라 달라 내지 않는다.
- 두 실행의 평가 세트 해시가 다르면 비교하지 않고 멈춘다.
- 겹침(같은 지은이·시리즈 쌍)은 DB가 있어야 셀 수 있어 내지 않는다. DB·외부 호출·인코딩이 없다.
"""

import json
import re
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app.seed.experiment import CollectionMissingError
from evals.collection.fetch import DATA_FILE as COLLECTION_FILE
from evals.recommendation.keys import load_fields
from evals.recommendation.labels import Labels, labels_file
from evals.recommendation.metrics import QueryScore, compare, mean, score_query
from evals.recommendation.sets import TOPIC_FILE, load_seeds, load_topic
from evals.recommendation.variants import VARIANT_SETS

EXIT_OK = 0
EXIT_PRECONDITION = 1
SPLIT_NAMES = {"tune": "조정", "check": "확인"}
TOPIC_GROUPS = (
    ("어린이", lambda q: q.children),
    ("일반", lambda q: not q.children),
    ("주제어", lambda q: q.style == "topic"),
    ("상황", lambda q: q.style == "mood"),
)
_FINGERPRINT = re.compile(r"^- (.+)$")


class CompareError(Exception):
    pass


@dataclass(frozen=True)
class Run:
    path: Path
    results: dict[str, dict[str, list[dict[str, Any]]]]  # 변형 → 항목 → 결과
    fingerprint: list[str]  # 요약의 "지문" 줄

    def value(self, name: str) -> str | None:
        prefix = f"{name}: "
        line = next((f for f in self.fingerprint if f.startswith(prefix)), None)
        return line[len(prefix) :] if line else None


def load_run(path: Path) -> Run:
    results_path, summary_path = path / "results.json", path / "summary.md"
    if not results_path.exists() or not summary_path.exists():
        raise CompareError(f"실행 폴더에 results.json과 summary.md가 있어야 합니다: {path}")
    results = json.loads(results_path.read_text(encoding="utf-8"))
    fingerprint, inside = [], False
    for line in summary_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line == "## 지문"
            continue
        match = _FINGERPRINT.match(line)
        if inside and match:
            fingerprint.append(match.group(1))
    return Run(path, results, fingerprint)


def set_of(base: Run, new: Run) -> str:
    """두 실행의 변형 이름으로 세트를 정한다(변형 표는 세트마다 따로다)."""
    names = set(base.results) | set(new.results)
    for set_name, table in VARIANT_SETS.items():
        if names <= set(table):
            return set_name
    raise CompareError(f"변형 이름으로 세트를 정할 수 없습니다: {', '.join(sorted(names))}")


def items_of(set_name: str) -> list[Any]:
    if set_name == "topic":
        return load_topic(TOPIC_FILE)
    try:
        fields = load_fields(COLLECTION_FILE)
    except CollectionMissingError as exc:
        raise CompareError(f"실험 장서 파일이 없습니다(기준 책의 분야를 읽는다): {exc}") from None
    seeds, histories = load_seeds(fields)
    return list(seeds if set_name == "similar" else histories)


def rescore(run: Run, variant: str, labels: Labels, ids: Sequence[str]) -> dict[str, QueryScore]:
    """그 변형의 항목별 결과를 지금 라벨로 다시 채점한다. 결과가 없는 항목은 빈 순위다."""
    rows = run.results.get(variant, {})
    return {
        item_id: score_query([r["key"] for r in rows.get(item_id, [])], labels.grades(item_id), {})
        for item_id in ids
    }


def _table(
    variants: Sequence[str],
    base: Mapping[str, Mapping[str, QueryScore]],
    new: Mapping[str, Mapping[str, QueryScore]],
    ids: Sequence[str],
) -> list[str]:
    lines = [
        "| 변형 | 항목 | 기준 nDCG@5 | 새 nDCG@5 | 차이 | 이김·비김·짐 | 95% 구간 "
        "| Hit@5 기준·새 | Recall@10 기준·새 | 라벨 없음 기준·새 |",
        "|" + " --- |" * 10,
    ]
    for name in variants:
        a = [base[name][i] for i in ids]
        b = [new[name][i] for i in ids]
        c = compare([s.ndcg for s in a], [s.ndcg for s in b])
        lines.append(
            f"| `{name}` | {len(ids)} | {mean([s.ndcg for s in a]):.3f}"
            f" | {mean([s.ndcg for s in b]):.3f} | {c.mean_diff:+.3f}"
            f" | {c.wins}·{c.ties}·{c.losses} | {c.low:+.3f} ~ {c.high:+.3f}"
            f" | {mean([s.hit for s in a]):.3f}·{mean([s.hit for s in b]):.3f}"
            f" | {mean([s.recall for s in a]):.3f}·{mean([s.recall for s in b]):.3f}"
            f" | {sum(s.unlabeled for s in a)}·{sum(s.unlabeled for s in b)} |"
        )
    return lines


def compare_runs(base: Run, new: Run, labels_path: Path | None = None) -> str:
    """두 실행을 비교한 요약. 세트 해시가 다르면 CompareError다."""
    base_hash, new_hash = base.value("평가 세트 해시"), new.value("평가 세트 해시")
    if base_hash != new_hash:
        raise CompareError(f"평가 세트 해시가 다릅니다: 기준 {base_hash}, 새 {new_hash}")
    set_name = set_of(base, new)
    labels = Labels(labels_path or labels_file(set_name))
    items = items_of(set_name)
    shared = [name for name in base.results if name in new.results]
    only = sorted(set(base.results) ^ set(new.results))
    lines = [
        "# 추천 실험: 실행 사이 비교",
        "",
        f"시각: {datetime.now():%Y-%m-%d %H:%M:%S}",
        "두 실행의 상위 10권을 지금 라벨로 다시 채점했다. 차이는 새 − 기준이다. DB·외부 호출 없음.",
        "",
        "## 지문",
        "",
        f"- 세트: {set_name}",
        f"- 평가 세트 해시: {base_hash}",
        f"- 지금 라벨 파일: {labels.path.name}",
        f"- 기준 실행: {base.path.name}",
        *[f"  - {line}" for line in base.fingerprint if not line.startswith("평가 세트 해시")],
        f"- 새 실행: {new.path.name}",
        *[f"  - {line}" for line in new.fingerprint if not line.startswith("평가 세트 해시")],
    ]
    if only:
        lines.append(f"- 한쪽에만 있어 비교하지 않은 변형: {', '.join(f'`{n}`' for n in only)}")
    ids_all = [item.id for item in items]
    base_scores = {name: rescore(base, name, labels, ids_all) for name in shared}
    new_scores = {name: rescore(new, name, labels, ids_all) for name in shared}
    for split, split_name in SPLIT_NAMES.items():
        part = [item for item in items if item.split == split]
        if not part:
            continue
        lines += ["", f"## {split_name} 세트 ({len(part)}개)", ""]
        lines += _table(shared, base_scores, new_scores, [item.id for item in part])
        if set_name == "topic":
            for label, belongs in TOPIC_GROUPS:
                group = [item.id for item in part if belongs(item)]
                if group:
                    lines += ["", f"### {split_name} · {label} ({len(group)}개)", ""]
                    lines += _table(shared, base_scores, new_scores, group)
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str]) -> int:
    if len(argv) != 2:
        print(
            "사용법: python -m evals.recommendation compare <기준 실행> <새 실행>", file=sys.stderr
        )
        return EXIT_PRECONDITION
    try:
        base, new = load_run(Path(argv[0])), load_run(Path(argv[1]))
        summary = compare_runs(base, new)
    except CompareError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_PRECONDITION
    out = new.path.parent / f"{new.path.name}-vs-{base.path.name}"
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.md").write_text(summary, encoding="utf-8")
    print(summary)
    print(f"결과: {out}")
    return EXIT_OK
