"""검색 평가 지표: 1위 적중, 5위 안 적중, MRR(찾는 책 순위의 역수 평균), 찾음 비율, 오탐 비율."""

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Outcome:
    kind: str
    text: str
    target: int | None
    ranked: tuple[int, ...]  # 결과 순서대로의 기관 도서 id


@dataclass(frozen=True)
class Score:
    kind: str
    count: int
    hit1: float
    hit5: float
    mrr: float
    found: float  # 찾는 책이 결과 어딘가에 있는 비율(자동완성 8개, 찾은 책 3권)
    any_rate: float  # 결과가 하나라도 있는 비율(오탐 문장은 낮아야 한다)


def rank(target: int | None, ranked: Sequence[int]) -> int | None:
    """1부터 센 순위. 없으면 None."""
    if target is None:
        return None
    return ranked.index(target) + 1 if target in ranked else None


def summarize(outcomes: Sequence[Outcome]) -> list[Score]:
    kinds: dict[str, list[Outcome]] = {}
    for outcome in outcomes:
        kinds.setdefault(outcome.kind, []).append(outcome)
    scores = []
    for kind, items in kinds.items():
        ranks = [rank(o.target, o.ranked) for o in items]
        n = len(items)
        scores.append(
            Score(
                kind=kind,
                count=n,
                hit1=sum(r == 1 for r in ranks) / n,
                hit5=sum(r is not None and r <= 5 for r in ranks) / n,
                mrr=sum(1 / r for r in ranks if r is not None) / n,
                found=sum(r is not None for r in ranks) / n,
                any_rate=sum(bool(o.ranked) for o in items) / n,
            )
        )
    return scores


def misses(outcomes: Sequence[Outcome], limit: int = 5) -> list[Outcome]:
    """5위 안에 들지 못한 질의(찾는 책이 있는 경우). 원인을 볼 때 쓴다."""
    missed = [o for o in outcomes if o.target is not None and (rank(o.target, o.ranked) or 99) > 5]
    return missed[:limit] if limit else missed
