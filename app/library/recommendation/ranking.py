"""순위 합치기와 결과 다양화. DB를 모르는 순수 함수다.

주제로 찾기(`topic.py`)가 신호별 순위를 여기서 합친다. 난수를 쓰지 않고 같은 입력에서 늘 같은
순서를 낸다. 매개변수(k, 가중치, 시리즈 상한, λ)는 추천 실험(`evals/recommendation`)이 정한다.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace

RRF_K = 60


@dataclass(frozen=True)
class Ranked:
    """합친 순위의 책 하나. `ranks`는 근거다: 신호 이름 → 그 신호에서의 순위(1부터)."""

    library_book_id: int
    score: float
    ranks: Mapping[str, int] = field(default_factory=dict)
    series_hidden: int = 0  # 시리즈 묶기로 빠진 같은 시리즈 권수


def fuse_rrf(
    rankings: Mapping[str, Sequence[int]],
    *,
    k: int = RRF_K,
    weights: Mapping[str, float] | None = None,
) -> list[Ranked]:
    """신호별 순위를 역순위 합으로 합친다. 점수는 신호마다 `가중치 / (k + 순위)`의 합이다.

    그 신호에 없는 책은 그 신호에서 0이다. 가중치가 0인 신호는 쓰지 않는다.
    점수가 같으면 가장 좋은 신호 순위, 그다음 기관 도서 id 순서다.
    """
    scores: dict[int, float] = {}
    ranks: dict[int, dict[str, int]] = {}
    for signal, ranking in rankings.items():
        weight = 1.0 if weights is None else weights.get(signal, 1.0)
        if weight <= 0:
            continue
        for position, book_id in enumerate(ranking, start=1):
            if signal in ranks.get(book_id, {}):
                continue  # 한 신호에 같은 책이 두 번 있으면 앞 순위만 쓴다
            scores[book_id] = scores.get(book_id, 0.0) + weight / (k + position)
            ranks.setdefault(book_id, {})[signal] = position
    fused = [Ranked(book_id, score, ranks[book_id]) for book_id, score in scores.items()]
    return sorted(fused, key=lambda r: (-r.score, min(r.ranks.values()), r.library_book_id))


def cap_series(
    items: Sequence[Ranked], series: Mapping[int, Sequence[str]], cap: int | None
) -> list[Ranked]:
    """같은 시리즈의 책을 상한까지만 남긴다. series는 기관 도서 id → 시리즈 키 목록이다.

    시리즈 키가 하나라도 겹치면 같은 시리즈다. 상한을 넘은 책은 빠지고, 남은 책 중 순위가 가장
    높은 같은 시리즈 책에 빠진 권수를 적는다. 시리즈 키가 없는 책은 묶이지 않는다.
    """
    if cap is None:
        return list(items)
    kept: list[Ranked] = []
    counts: dict[str, int] = {}
    first: dict[str, int] = {}  # 시리즈 키 → kept에서 그 시리즈의 첫 책 위치
    for item in items:
        keys = list(series.get(item.library_book_id, ()))
        full = [key for key in keys if counts.get(key, 0) >= cap]
        if full:
            head = min(first[key] for key in full)
            kept[head] = replace(kept[head], series_hidden=kept[head].series_hidden + 1)
            continue
        for key in keys:
            counts[key] = counts.get(key, 0) + 1
            first.setdefault(key, len(kept))
        kept.append(item)
    return kept


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def mmr(
    items: Sequence[Ranked], vectors: Mapping[int, Sequence[float]], lam: float | None
) -> list[Ranked]:
    """MMR로 순서를 다시 정한다.

    다음 책은 `λ × 관련도 − (1 − λ) × 이미 고른 책과의 최대 유사도`가 가장 큰 책이다. 관련도는
    합친 점수를 후보 안에서 0~1로 맞춘 값이고, 책 사이 유사도는 벡터의 코사인이다. 벡터가 없는
    책의 유사도는 0이다. λ가 없거나 1이면 순서를 바꾸지 않는다. 값이 같으면 원래 앞선 책이다.
    """
    if lam is None or lam >= 1 or len(items) < 2:
        return list(items)
    low = min(item.score for item in items)
    span = max(item.score for item in items) - low
    relevance = [(item.score - low) / span if span else 1.0 for item in items]
    similarity: dict[tuple[int, int], float] = {}

    def between(i: int, j: int) -> float:
        key = (min(i, j), max(i, j))
        if key not in similarity:
            a = vectors.get(items[i].library_book_id)
            b = vectors.get(items[j].library_book_id)
            similarity[key] = _cosine(a, b) if a is not None and b is not None else 0.0
        return similarity[key]

    chosen: list[int] = []
    rest = list(range(len(items)))
    while rest:
        best = max(
            rest,
            key=lambda i: (
                lam * relevance[i] - (1 - lam) * max((between(i, j) for j in chosen), default=0.0),
                -i,
            ),
        )
        chosen.append(best)
        rest.remove(best)
    return [items[i] for i in chosen]
