"""[catalog/related-recommendation] 벡터 근거만 있는 책의 최소 유사도: 진단 규칙(결정 10)."""

from evals.recommendation.threshold import Point, choose_threshold, cut_at


def _points(split: str, grade: int, *cosines: float) -> list[Point]:
    return [Point(split, "s", f"k{grade}-{c}", c, grade) for c in cosines]


def test_cut_at_counts_by_grade() -> None:
    points = _points("tune", 0, 0.3, 0.4) + _points("tune", 2, 0.5, 0.6)
    cut = cut_at(points, 0.45)
    assert (cut.zero_removed, cut.two_removed) == (1.0, 0.0)


def test_separable_labels_pick_largest_threshold() -> None:
    tune = _points("tune", 0, 0.30, 0.32, 0.34, 0.36) + _points("tune", 2, 0.60, 0.62, 0.70)
    check = _points("check", 0, 0.33) + _points("check", 2, 0.65)
    # 0.37 ~ 0.60까지 0을 모두 빼고 2는 하나도 빼지 않는다. 가장 큰 것은 0.60
    assert choose_threshold(tune, check) == 0.60


def test_overlapping_labels_give_no_threshold() -> None:
    tune = _points("tune", 0, 0.40, 0.42, 0.44, 0.46) + _points("tune", 2, 0.41, 0.43, 0.45)
    check = _points("check", 0, 0.42) + _points("check", 2, 0.43)
    assert choose_threshold(tune, check) is None


def test_check_must_agree() -> None:
    tune = _points("tune", 0, 0.30, 0.32) + _points("tune", 2, 0.60, 0.62)
    check = _points("check", 0, 0.70) + _points("check", 2, 0.35)  # 확인 세트는 반대
    assert choose_threshold(tune, check) is None


def test_no_zero_labels() -> None:
    assert choose_threshold(_points("tune", 2, 0.5), []) is None
