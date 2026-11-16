"""고정 표본 검수. 라벨을 Claude가 달고 사람은 이 표본만 본다.

표본은 실행 결과를 보지 않고 정한다. 등급(2·1·0)마다 고르게, 항목 id와 책 키의 SHA-256 순서로
뽑아 같은 라벨 파일이면 늘 같다. 등급은 초안의 등급으로 본다(사람이 고쳐도 표본이 바뀌지 않는다).
사람이 맞다고 하거나 고친 라벨은 단 쪽이 `user`가 되고, 고치기 전 초안 등급이 `draft`에 남는다.
"""

import hashlib
import json
from collections.abc import Collection
from pathlib import Path

from evals.recommendation.labels import GRADES, USER, Labels

SAMPLE_SIZES = {"similar": 25, "history": 20, "topic": 30}
# 보충 라벨만 보는 표본(`--since`). 세 세트 합 20건(`add-bibliographic-sources` design 결정 9)
SUPPLEMENT_SAMPLE_SIZES = {"topic": 8, "similar": 7, "history": 5}


def new_pairs(labels: Labels, since: Path) -> set[tuple[str, str]]:
    """백업 라벨 파일(`since`)에 없던 (항목 id, 책 키). 이번에 단 보충 라벨이다."""
    before = json.loads(since.read_text(encoding="utf-8")) if since.exists() else {}
    return {
        (item_id, key)
        for item_id, entries in labels.items.items()
        for key in entries
        if key not in before.get(item_id, {})
    }


def _order(item_id: str, key: str) -> str:
    return hashlib.sha256(f"{item_id}|{key}".encode()).hexdigest()


def _drafted(entry: dict) -> int:
    return entry.get("draft", entry["grade"])


def pick_sample(
    labels: Labels, size: int, only: Collection[tuple[str, str]] | None = None
) -> list[tuple[str, str]]:
    """표본의 (항목 id, 책 키). 등급마다 고르게 나누고, 모자란 등급의 몫은 다른 등급이 채운다.

    `only`가 있으면 그 라벨 안에서만 뽑는다(보충 라벨만 보는 표본).
    """
    by_grade: dict[int, list[tuple[str, str]]] = {grade: [] for grade in GRADES}
    for item_id, entries in labels.items.items():
        for key, entry in entries.items():
            if only is None or (item_id, key) in only:
                by_grade[_drafted(entry)].append((item_id, key))
    for pairs in by_grade.values():
        pairs.sort(key=lambda pair: _order(*pair))
    order = sorted(GRADES, reverse=True)  # 나머지는 2, 1, 0 순서로 준다
    quota = {grade: size // len(order) for grade in order}
    for grade in order[: size % len(order)]:
        quota[grade] += 1
    taken = {grade: min(quota[grade], len(by_grade[grade])) for grade in order}
    spare = size - sum(taken.values())
    while spare > 0:
        room = [grade for grade in order if taken[grade] < len(by_grade[grade])]
        if not room:
            break
        for grade in room:
            if spare > 0:
                taken[grade] += 1
                spare -= 1
    picked = [pair for grade in order for pair in by_grade[grade][: taken[grade]]]
    return sorted(picked, key=lambda pair: _order(*pair))


def sample_stats(
    labels: Labels, size: int, only: Collection[tuple[str, str]] | None = None
) -> dict:
    """표본 수, 본 수, 고친 수, 등급별 (본 수, 맞은 수)."""
    sample = pick_sample(labels, size, only)
    per_grade = {grade: [0, 0] for grade in GRADES}
    seen = changed = 0
    for item_id, key in sample:
        entry = labels.items[item_id][key]
        if entry.get("by", USER) != USER:
            continue
        seen += 1
        agreed = _drafted(entry) == entry["grade"]
        changed += not agreed
        per_grade[_drafted(entry)][0] += 1
        per_grade[_drafted(entry)][1] += agreed
    return {"size": len(sample), "seen": seen, "changed": changed, "per_grade": per_grade}


def sample_line(labels: Labels, size: int, only: Collection[tuple[str, str]] | None = None) -> str:
    """실행 요약의 한 줄: 표본 수, 등급별 일치율(사람이 고치지 않은 비율), 보지 않은 표본 수."""
    stats = sample_stats(labels, size, only)
    seen = stats["seen"]
    rate = f"{(seen - stats['changed']) / seen:.0%}" if seen else "-"
    grades = ", ".join(
        f"{grade}: {agreed}/{count}"
        for grade, (count, agreed) in sorted(stats["per_grade"].items())
    )
    return (
        f"- 표본 검수: 표본 {stats['size']}건, 일치율 {rate} (초안 등급별 맞음/본 것 {grades}),"
        f" 보지 않은 표본 {stats['size'] - seen}건"
    )
