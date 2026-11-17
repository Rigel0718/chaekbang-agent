"""[platform/recommendation-experiments] 키워드 순위가 빈 질의 진단. DB·임베딩 서버 없음."""

from pathlib import Path

import pytest

from evals.recommendation.keyword_empty import (
    EMPTY,
    MATCHED,
    by_evidence,
    groups,
    keyword_empty,
    report,
)
from evals.recommendation.labels import BEFORE, Labels
from evals.recommendation.sets import TopicQuery


def _query(query_id: str) -> TopicQuery:
    return TopicQuery(query_id, "문장", ("낱말",), False, "topic", ("science",), "tune")


def _rows(keyword: bool) -> list[dict]:
    rows = [{"key": f"k{i}", "ranks": {"vector": i + 1}} for i in range(5)]
    if keyword:
        rows[2]["ranks"]["keyword"] = 1
    return rows


def test_diagnosis_table(tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 키워드 순위가 빈 질의 진단 / 진단 표"""
    labels = Labels(tmp_path / "topic.json")
    ids = ["e1", "e2", "m1", "m2", "m3"]
    for query_id in ids:
        labels.put_many(query_id, {"k0": 2, "k1": 1, "k2": 0}, BEFORE)
    results = {q: _rows(keyword=q.startswith("m")) for q in ids}
    found = {
        g.name: g for g in groups(results, [_query(q) for q in ids], labels) if g.split == "tune"
    }
    assert len(found[EMPTY].queries) == 2 and len(found[MATCHED].queries) == 3
    assert found[EMPTY].grades == {"0": 2, "1": 2, "2": 2, "없음": 4}
    assert found[EMPTY].ndcg == pytest.approx(1.0)
    text = report(list(found.values()), "hybrid-best")
    assert f"| 조정 | {EMPTY} | 2 |" in text and f"| 조정 | {MATCHED} | 3 |" in text


def test_diagnosis_without_server(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 키워드 순위가 빈 질의 진단 / 서버 없이

    진단은 저장된 결과와 라벨만 읽는다. 인코더를 만들거나 부르면 실패하게 해 둔다.
    """
    import app.central.external.tei as tei

    def refuse(*args, **kwargs):
        raise AssertionError("인코더를 부르면 안 된다")

    monkeypatch.setattr(tei.TeiEmbedder, "__init__", refuse)
    labels = Labels(tmp_path / "topic.json")
    labels.put_many("e1", {"k0": 1}, BEFORE)
    assert keyword_empty(_rows(keyword=False)) and not keyword_empty(_rows(keyword=True))
    assert groups({"e1": _rows(False)}, [_query("e1")], labels)[0].queries == ("e1",)


def test_books_by_evidence(tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 키워드 순위가 빈 질의 진단 / 진단 표 (근거별 책)"""
    labels = Labels(tmp_path / "topic.json")
    labels.put_many("m1", {"k0": 2, "k2": 1}, BEFORE)
    rows = _rows(keyword=True)
    rows[0]["ranks"] = {"keyword": 2}
    counts = by_evidence({"m1": rows}, [_query("m1")], labels)
    assert counts[("tune", "키워드만")] == {"0": 0, "1": 0, "2": 1, "없음": 0}
    assert counts[("tune", "둘 다")] == {"0": 0, "1": 1, "2": 0, "없음": 0}
    assert counts[("tune", "벡터만")]["없음"] == 3
