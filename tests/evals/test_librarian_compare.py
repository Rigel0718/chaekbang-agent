"""[agent/librarian] AI 사서 평가 실행 비교. 저장된 기록만 읽는다(LLM·DB 없음)."""

import json
from pathlib import Path

import openai
import pytest

from evals.librarian.compare import main


def _record(scenario: str, *, met: bool, children: bool, topic_met, tools, ms: int) -> dict:
    turn = {
        "tools": tools,
        "input_tokens": 100,
        "output_tokens": 10,
        "steps": [{"duration_ms": ms}, {"duration_ms": None}],
    }
    return {
        "id": scenario,
        "expectation_met": met,
        "violations": {},
        "children_judged": children,
        "expected_children": False,
        "topic_met": topic_met,
        "turns": [turn],
    }


def _write(folder: Path, records: list[dict]) -> None:
    folder.mkdir()
    for index, record in enumerate(records, start=1):
        path = folder / f"{index:02d}-{record['id']}.json"
        path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")


def test_compare_runs_side_by_side(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """[agent/librarian] 주제 요청에 답함 (전후 비교 출력, LLM을 부르지 않음)"""

    def refuse(*args, **kwargs):
        raise AssertionError("LLM을 부르면 안 된다")

    monkeypatch.setattr(openai, "AsyncOpenAI", refuse)
    tools = ["search_collection", "search_collection", "submit_answer"]
    _write(tmp_path / "before", [
        _record("dinosaur", met=True, children=False, topic_met=True, tools=tools, ms=1500),
        _record("parenting", met=False, children=True, topic_met=None, tools=tools[:1], ms=500),
    ])  # fmt: skip
    _write(tmp_path / "after", [
        _record("dinosaur", met=True, children=False, topic_met=False, tools=tools[:1], ms=2000),
    ])  # fmt: skip
    out = tmp_path / "compare.md"
    code = main([str(tmp_path / "before"), str(tmp_path / "after"), "--out", str(out)])
    text = capsys.readouterr().out
    assert code == 0 and out.read_text(encoding="utf-8") == text.removesuffix("\n")
    assert "| 기대 불일치 | 1 | 0 |" in text
    assert "| 어린이 판단 불일치 | 1 | 0 |" in text
    assert "| 주제 낱말 일치 | 1/1 | 0/1 |" in text
    assert "| 검색 tool 호출 | 3 | 1 |" in text
    assert "| parenting | × 위반0 어린이× - 검색1 0.5s | 없음 |" in text


def test_compare_missing_run(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """[agent/librarian] 주제 요청에 답함 (전후 비교: 없는 실행 폴더)"""
    assert main([str(tmp_path / "nothing")]) == 1
    assert "실행 폴더가 없습니다" in capsys.readouterr().err
