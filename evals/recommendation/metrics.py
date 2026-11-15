"""추천 실험의 지표. DB를 모르는 순수 함수다.

- nDCG@5: 라벨 0·1·2의 이득을 `2^라벨 − 1`(0, 1, 3)로, 순위 할인은 `1 / log2(순위 + 1)`.
  이상적 순위는 그 질의에 달린 라벨 전체로 만든다. AI 사서가 최대 5권을 낸다.
- Hit@5: 라벨 2인 책이 상위 5권에 하나라도 있다.
- Recall@10: 라벨 1 이상인 책 중 상위 10권에 든 비율. 분모는 그 수와 10 중 작은 값.
- 겹침: 상위 5권에서 같은 지은이인 쌍 + 같은 시리즈인 쌍.
- 라벨 없는 책은 0으로 센다. 그 수를 따로 적는다.

질의가 적어 평균만으로는 읽을 수 없다. 기준 변형과 질의별 차이로 이김·비김·짐을 세고, 고정 시드
부트스트랩으로 평균 차이의 95% 구간을 낸다.
"""

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import combinations

TOP = 5
DEEP = 10
BOOTSTRAP_ROUNDS = 2000
BOOTSTRAP_SEED = 0
_EPSILON = 1e-12


@dataclass(frozen=True)
class QueryScore:
    ndcg: float
    hit: float
    recall: float
    overlap: int
    unlabeled: int  # 상위 5권 중 라벨 없는 책


@dataclass(frozen=True)
class Comparison:
    wins: int
    ties: int
    losses: int
    mean_diff: float
    low: float  # 평균 차이의 95% 구간
    high: float


def _dcg(grades: Sequence[int]) -> float:
    return sum((2**g - 1) / math.log2(i + 2) for i, g in enumerate(grades))


def ndcg(ranked: Sequence[int | None], labeled: Sequence[int], k: int = TOP) -> float:
    """ranked는 결과 순서대로의 라벨(없으면 None), labeled는 그 질의의 라벨 전체다."""
    ideal = _dcg(sorted(labeled, reverse=True)[:k])
    return _dcg([g or 0 for g in ranked[:k]]) / ideal if ideal else 0.0


def hit(ranked: Sequence[int | None], k: int = TOP) -> float:
    return 1.0 if any(g == 2 for g in ranked[:k]) else 0.0


def recall(ranked: Sequence[int | None], labeled: Sequence[int], k: int = DEEP) -> float:
    relevant = sum(1 for g in labeled if g >= 1)
    found = sum(1 for g in ranked[:k] if g is not None and g >= 1)
    return found / min(relevant, k) if relevant else 0.0


def overlap(groups: Sequence[tuple[Sequence[str], Sequence[str]]]) -> int:
    """groups는 책마다 (지은이 키, 시리즈 키)다. 지은이가 겹치는 쌍 수 + 시리즈가 겹치는 쌍 수."""
    pairs = 0
    for (authors_a, series_a), (authors_b, series_b) in combinations(groups, 2):
        pairs += bool(set(authors_a) & set(authors_b)) + bool(set(series_a) & set(series_b))
    return pairs


def score_query(
    ranked_keys: Sequence[str],
    labels: Mapping[str, int],
    groups: Mapping[str, tuple[Sequence[str], Sequence[str]]],
) -> QueryScore:
    """ranked_keys는 결과 순서대로의 책 키, labels는 그 질의의 책 키 → 라벨이다."""
    grades = [labels.get(key) for key in ranked_keys]
    labeled = list(labels.values())
    return QueryScore(
        ndcg=ndcg(grades, labeled),
        hit=hit(grades),
        recall=recall(grades, labeled),
        overlap=overlap([groups.get(key, ((), ())) for key in ranked_keys[:TOP]]),
        unlabeled=sum(1 for g in grades[:TOP] if g is None),
    )


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def compare(
    base: Sequence[float],
    other: Sequence[float],
    *,
    rounds: int = BOOTSTRAP_ROUNDS,
    seed: int = BOOTSTRAP_SEED,
) -> Comparison:
    """같은 질의 순서의 두 변형 점수를 짝지어 비교한다. 차이는 other − base다."""
    diffs = [b - a for a, b in zip(base, other, strict=True)]
    wins = sum(1 for d in diffs if d > _EPSILON)
    losses = sum(1 for d in diffs if d < -_EPSILON)
    if not diffs:
        return Comparison(0, 0, 0, 0.0, 0.0, 0.0)
    rng = random.Random(seed)
    n = len(diffs)
    means = sorted(mean([diffs[rng.randrange(n)] for _ in range(n)]) for _ in range(rounds))
    low = means[int(rounds * 0.025)]
    high = means[min(rounds - 1, int(rounds * 0.975))]
    return Comparison(wins, n - wins - losses, losses, mean(diffs), low, high)
