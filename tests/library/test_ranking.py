"""[catalog/topic-recommendation] 순위 합치기, 시리즈 묶기, 결과 다양화. DB 없이 돈다."""

import pytest

from app.library.recommendation.ranking import Ranked, cap_series, fuse_rrf, mmr
from tests.embedding_helpers import unit


def _ids(items) -> list[int]:
    return [item.library_book_id for item in items]


def test_rrf_score() -> None:
    """[catalog/topic-recommendation] 순위 합치기 / 점수 계산"""
    fused = fuse_rrf({"keyword": [1, 8, 9], "vector": [2, 7, 1]}, k=60)
    by_id = {item.library_book_id: item for item in fused}
    assert by_id[1].score == pytest.approx(1 / 61 + 1 / 63)
    assert by_id[2].score == pytest.approx(1 / 61)
    assert _ids(fused)[:2] == [1, 2]


def test_rrf_signal_weight() -> None:
    """[catalog/topic-recommendation] 순위 합치기 / 신호 가중치"""
    fused = fuse_rrf(
        {"keyword": [5, 6, 7], "vector": [3, 2, 1]}, weights={"keyword": 0, "vector": 1}
    )
    assert _ids(fused) == [3, 2, 1]
    doubled = fuse_rrf({"keyword": [5], "vector": [3]}, k=60, weights={"keyword": 2, "vector": 1})
    assert _ids(doubled) == [5, 3]
    assert doubled[0].score == pytest.approx(2 / 61)


def test_rrf_evidence() -> None:
    """[catalog/topic-recommendation] 순위 합치기 / 근거"""
    fused = fuse_rrf({"keyword": [4, 5], "vector": [4, 6]})
    by_id = {item.library_book_id: item for item in fused}
    assert dict(by_id[5].ranks) == {"keyword": 2}
    assert "vector" not in by_id[5].ranks
    assert dict(by_id[4].ranks) == {"keyword": 1, "vector": 1}


def test_rrf_tie_breaks_by_id() -> None:
    """[catalog/topic-recommendation] 순위 합치기 / 같은 점수"""
    fused = fuse_rrf({"keyword": [9, 3], "vector": [2, 5]})
    assert _ids(fused) == [2, 9, 3, 5]
    # 점수가 같아도 가장 좋은 신호 순위가 앞선 책이 먼저다
    mixed = fuse_rrf({"a": [1, 7], "b": [8, 7]}, k=0, weights={"a": 1, "b": 1})
    assert mixed[0].library_book_id in (1, 8) and _ids(mixed)[:2] == [1, 8]


def _ranked(*ids: int) -> list[Ranked]:
    return [Ranked(book_id, 1.0 - i * 0.01, {"keyword": i + 1}) for i, book_id in enumerate(ids)]


def test_series_cap_one() -> None:
    """[catalog/topic-recommendation] 시리즈 묶기 / 상한 1"""
    series = {11: ["마법천자문"], 12: ["마법천자문"], 14: ["마법천자문", "다른이름"]}
    kept = cap_series(_ranked(11, 12, 13, 14, 15), series, 1)
    assert _ids(kept) == [11, 13, 15]
    assert kept[0].series_hidden == 2
    assert [item.series_hidden for item in kept[1:]] == [0, 0]
    assert _ids(cap_series(_ranked(11, 12, 13, 14, 15), series, 2)) == [11, 12, 13, 15]
    assert _ids(cap_series(_ranked(11, 12, 13), series, None)) == [11, 12, 13]


def test_series_cap_leaves_books_without_series() -> None:
    """[catalog/topic-recommendation] 시리즈 묶기 / 시리즈 없는 책"""
    kept = cap_series(_ranked(21, 22), {}, 1)
    assert _ids(kept) == [21, 22]
    assert [item.series_hidden for item in kept] == [0, 0]


def test_mmr_moves_similar_book_back() -> None:
    """[catalog/topic-recommendation] 결과 다양화 / 비슷한 책 뒤로"""
    items = [Ranked(1, 1.00), Ranked(2, 0.99), Ranked(3, 0.98)]
    vectors = {1: unit(1), 2: unit(1), 3: unit(0, 1)}
    assert _ids(mmr(items, vectors, 0.5)) == [1, 3, 2]
    # 벡터가 없는 책의 유사도는 0이다
    assert _ids(mmr(items, {1: unit(1), 2: unit(1)}, 0.5)) == [1, 3, 2]


def test_mmr_lambda_one_keeps_order() -> None:
    """[catalog/topic-recommendation] 결과 다양화 / λ가 1"""
    items = [Ranked(1, 1.00), Ranked(2, 0.99), Ranked(3, 0.98)]
    vectors = {1: unit(1), 2: unit(1), 3: unit(0, 1)}
    assert _ids(mmr(items, vectors, 1.0)) == [1, 2, 3]
    assert _ids(mmr(items, vectors, None)) == [1, 2, 3]
