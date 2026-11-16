"""[platform/recommendation-experiments] 실행 사이 비교: 두 실행을 지금 라벨로 다시 채점한다."""

import json
from pathlib import Path

import pytest

from evals.recommendation import compare as compare_module
from evals.recommendation.compare import (
    CompareError,
    compare_runs,
    load_run,
    main,
)
from evals.recommendation.sets import load_topic

QUERIES = load_topic()
IDS = [q.id for q in QUERIES]


def _run(
    tmp_path: Path,
    name: str,
    results: dict,
    set_hash: str = "54201ec7acec",
    extra: tuple[str, ...] = (),
) -> Path:
    path = tmp_path / name
    path.mkdir()
    (path / "results.json").write_text(json.dumps(results, ensure_ascii=False), encoding="utf-8")
    fingerprint = [f"- 평가 세트 해시: {set_hash}", "- 라벨 해시: aaaaaaaaaaaa"]
    fingerprint += [f"- {line}" for line in extra]
    summary = ["# 추천 실험: 주제로 찾기", "", "## 지문", "", *fingerprint, "", "## 변형", ""]
    (path / "summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    return path


def _results(key_of) -> dict:  # noqa: ANN001
    """변형 둘(`current`, `hybrid-k60`)의 질의마다 상위 1권."""
    return {
        variant: {qid: [{"key": key_of(variant, qid), "grade": None}] for qid in IDS}
        for variant in ("current", "hybrid-k60")
    }


def _labels(tmp_path: Path, grades: dict) -> Path:
    path = tmp_path / "topic.json"
    rows = {
        qid: {
            key: {"grade": grade, "stage": "before", "by": "claude"} for key, grade in books.items()
        }
        for qid, books in grades.items()
    }
    path.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return path


def _row(summary: str, section: str, variant: str) -> str:
    part = summary.split(f"## {section}")[1]
    return next(line for line in part.splitlines() if line.startswith(f"| `{variant}`"))


def test_same_run_ties(tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 실행 사이 비교 / 같은 실행"""
    run = _run(tmp_path, "a", _results(lambda v, q: f"isbn:{q}-good"))
    labels = _labels(tmp_path, {q: {f"isbn:{q}-good": 2} for q in IDS})
    summary = compare_runs(load_run(run), load_run(run), labels)
    for variant in ("current", "hybrid-k60"):
        row = _row(summary, "조정 세트", variant)
        assert "| +0.000 |" in row
        assert "| 0·20·0 |" in row
        assert "+0.000 ~ +0.000" in row


def test_different_set_stops(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """[platform/recommendation-experiments] 실행 사이 비교 / 세트가 다름"""
    base = _run(tmp_path, "a", _results(lambda v, q: "isbn:x"), set_hash="111111111111")
    new = _run(tmp_path, "b", _results(lambda v, q: "isbn:x"), set_hash="222222222222")
    with pytest.raises(CompareError, match="평가 세트 해시"):
        compare_runs(load_run(base), load_run(new))
    assert main([str(base), str(new)]) == compare_module.EXIT_PRECONDITION
    err = capsys.readouterr().err
    assert "111111111111" in err and "222222222222" in err
    assert not (tmp_path / "b-vs-a").exists()


def test_current_labels_rescore_both(tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 실행 사이 비교 / 지금 라벨로 다시 채점"""
    base = _run(tmp_path, "a", _results(lambda v, q: f"isbn:{q}-old"))
    new = _run(tmp_path, "b", _results(lambda v, q: f"isbn:{q}-new"))
    before = _labels(tmp_path, {q: {f"isbn:{q}-old": 2, f"isbn:{q}-new": 0} for q in IDS})
    summary = compare_runs(load_run(base), load_run(new), before)
    assert "| 0·0·20 |" in _row(summary, "조정 세트", "current")  # 새 실행이 모두 짐
    # 기준 실행 뒤에 새 책의 라벨을 0에서 2로 고치면 두 실행이 같은 점수가 된다
    after = _labels(tmp_path, {q: {f"isbn:{q}-old": 2, f"isbn:{q}-new": 2} for q in IDS})
    summary = compare_runs(load_run(base), load_run(new), after)
    assert "| 0·20·0 |" in _row(summary, "조정 세트", "current")


def test_variant_on_one_side(tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 실행 사이 비교 / 한쪽에만 있는 변형"""
    results = _results(lambda v, q: "isbn:x")
    base = _run(tmp_path, "a", results | {"vec-text": results["current"]})
    new = _run(tmp_path, "b", results)
    summary = compare_runs(load_run(base), load_run(new), _labels(tmp_path, {}))
    assert "한쪽에만 있어 비교하지 않은 변형: `vec-text`" in summary
    assert "| `vec-text`" not in summary


def test_no_encoding_or_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """[platform/recommendation-experiments] 실행 사이 비교 / 인코딩 없음"""
    from app.central.external import tei

    def fail(*args, **kwargs):
        raise AssertionError("비교는 인코딩하지 않는다")

    monkeypatch.setattr(tei.TeiEmbedder, "encode_queries", fail)
    monkeypatch.setattr(tei.TeiEmbedder, "encode_documents", fail)
    base = _run(
        tmp_path, "a", _results(lambda v, q: "isbn:x"), extra=("공식 서지 출처: yes24 472",)
    )
    new = _run(
        tmp_path, "b", _results(lambda v, q: "isbn:x"), extra=("공식 서지 출처: data4library 470",)
    )
    labels = _labels(tmp_path, {})
    monkeypatch.setattr(compare_module, "labels_file", lambda name: labels)
    assert main([str(base), str(new)]) == compare_module.EXIT_OK
    summary = (tmp_path / "b-vs-a" / "summary.md").read_text(encoding="utf-8")
    assert "공식 서지 출처: yes24 472" in summary
    assert "공식 서지 출처: data4library 470" in summary
    assert "## 확인 세트 (10개)" in summary
    assert "### 조정 · 어린이" in summary
