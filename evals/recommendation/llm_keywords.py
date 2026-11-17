"""주제 세트의 사람이 쓴 낱말을 대화 추천 평가가 받은 실제 LLM 낱말로 바꾼다.

대화 추천 평가 실행(`evals/conversation/data/runs/<실행>/items.json`)에서 주제 항목마다 마지막
턴의 첫 검색 tool 호출 낱말을 쓴다. 검색 tool을 부르지 않은 항목은 뺀다. LLM을 부르지 않는다.
"""

import json
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from evals.recommendation.sets import TopicQuery

CONVERSATION_RUNS = Path(__file__).parent.parent / "conversation" / "data" / "runs"
SEARCH_TOOLS = ("search_collection", "search_children_books")


def run_path(value: Path) -> Path:
    return value if value.exists() else CONVERSATION_RUNS / value


def first_keywords(path: Path) -> dict[str, list[str]]:
    """주제 항목 id → 첫 검색 낱말. 검색 tool을 부르지 않은 항목은 없다."""
    document = json.loads((run_path(path) / "items.json").read_text(encoding="utf-8"))
    found = {}
    for item in document["items"]:
        if item["set_name"] != "topic":
            continue
        search = next((c for c in item["calls"] if c["name"] in SEARCH_TOOLS), None)
        if search is not None and search["input"].get("keywords"):
            found[item["id"]] = list(search["input"]["keywords"])
    return found


def with_llm_keywords(
    queries: Sequence[TopicQuery], path: Path
) -> tuple[list[TopicQuery], list[str]]:
    """낱말을 바꾼 질의와 뺀 항목 id(검색 없음)."""
    found = first_keywords(path)
    kept = [replace(q, keywords=tuple(found[q.id])) for q in queries if q.id in found]
    return kept, [q.id for q in queries if q.id not in found]


def keywords_line(path: Path, skipped: Sequence[str]) -> str:
    """실행 요약의 지문 줄: 낱말을 가져온 대화 평가 실행과 검색 없어 뺀 항목 수."""
    names = f" ({', '.join(skipped)})" if skipped else ""
    return f"- 실제 LLM 낱말: 대화 평가 `{path}`, 검색 없어 뺀 항목 {len(skipped)}개{names}"
