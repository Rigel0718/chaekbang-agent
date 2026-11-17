"""[platform/conversation-recommendation-evals] 대화 추천 평가. 가짜 LLM·가짜 인코더로 돈다.

실험 장서는 테스트 안에서 만든 작은 문서(지어낸 서지)다. 저장소에 YES24 값을 넣지 않는다.
"""

import json
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.agent.models import AgentStep, StepKind
from app.core.config import get_settings
from app.features.children.rules import is_children_request
from app.features.children.service import related_scope as children_related_scope
from app.features.children.tools import children_extension
from app.library.hooks import register_related_scope
from app.library.librarian import build_librarian_profiles
from app.library.models.library import Library
from app.library.services import chat
from app.seed.experiment import LIBRARY_NAME
from evals.conversation import compare as conversation_compare
from evals.conversation.__main__ import item_run
from evals.conversation.capture import Capture, capturing
from evals.conversation.catalog import load_experiment
from evals.conversation.compare import SavedRun, SetMismatchError, compare_runs
from evals.conversation.items import (
    ANYTHING_CHILDREN_TEXT,
    ANYTHING_TEXT,
    SIMILAR_CHILDREN_TEXT,
    SIMILAR_TEXT,
    ChatItem,
    Group,
    build_items,
)
from evals.conversation.score import (
    NOT_POOLED,
    ItemRun,
    cost,
    exit_code,
    group_rows,
    results,
    score_keys,
    summary,
)
from evals.librarian.__main__ import rollback_session
from evals.librarian.runner import run_scenario
from evals.recommendation.cache import CachedEmbedder
from evals.recommendation.draft import read_pool_results
from evals.recommendation.keys import fields_of
from evals.recommendation.label import pool_keys
from evals.recommendation.labels import Labels
from evals.recommendation.metrics import ndcg
from evals.recommendation.sets import History, Seed, TopicQuery
from tests.agent.fakes import FakeLlm
from tests.embedding_helpers import FakeEmbedder
from tests.helpers import make_isbn
from tests.library.librarian_helpers import call, search, submit, turn
from tests.yes24_helpers import item


def _rows(count: int = 12) -> list[dict]:
    rows = []
    for i in range(count):
        children = i % 3 == 0
        rows.append(
            {
                "field": "children" if children else "general",
                "rank": i + 1,
                "item": item(
                    make_isbn(700 + i),
                    title=f"대화 평가 책 {i}",
                    author=f"작가{i} 지음",
                    goodsSortNm="국내도서-어린이" if children else "국내도서-인문",
                    series=[],
                ),
            }
        )
    return rows


def _write_collection(tmp_path: Path) -> Path:
    path = tmp_path / "collection.json"
    path.write_text(json.dumps({"fetched_on": "2026-11-17", "books": _rows()}), encoding="utf-8")
    return path


def _cached(tmp_path: Path, inner: FakeEmbedder | None = None) -> CachedEmbedder:
    return CachedEmbedder(inner or FakeEmbedder(), tmp_path / "q.json", tmp_path / "d.json")


async def _load(session: AsyncSession, tmp_path: Path, inner: FakeEmbedder | None = None):
    return await load_experiment(
        session,
        collection_path=_write_collection(tmp_path),
        sources_path=tmp_path / "no-sources.json",
        embedder=_cached(tmp_path, inner),
    )


# --- 실험 장서로 평가 ---


async def test_same_book_keys(session: AsyncSession, tmp_path: Path) -> None:
    """[platform/conversation-recommendation-evals] 실험 장서로 평가 / 같은 책 키"""
    catalog = await _load(session, tmp_path)
    expected = set(fields_of(_rows()))
    assert set(catalog.keys) == expected
    assert catalog.vectors > 0
    assert catalog.children and catalog.children <= set(catalog.keys.values())


async def test_doc_vector_cache(session: AsyncSession, tmp_path: Path) -> None:
    """[platform/conversation-recommendation-evals] 실험 장서로 평가 / 문서 벡터 캐시"""
    first = await _load(session, tmp_path)
    await session.rollback()
    again = FakeEmbedder()
    second = await _load(session, tmp_path, again)
    assert again.document_calls == []
    assert second.vectors == first.vectors


async def test_rollback_leaves_nothing(tmp_path: Path) -> None:
    """[platform/conversation-recommendation-evals] 실험 장서로 평가 / 되돌림"""
    url = get_settings().test_database_url
    assert url
    async with rollback_session(url) as s:
        catalog = await _load(s, tmp_path)
        assert catalog.keys
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with AsyncSession(engine) as s:
            left = await s.scalar(
                select(func.count()).select_from(Library).where(Library.name == LIBRARY_NAME)
            )
    finally:
        await engine.dispose()
    assert left == 0


# --- 세트 항목을 대화로 ---


def test_item_shapes() -> None:
    """[platform/conversation-recommendation-evals] 세트 항목을 대화로 / 비슷한 책 항목"""
    keys = {"isbn:1": 1, "isbn:2": 2, "isbn:3": 3, "acc:EX00004": 4}
    topics = [
        TopicQuery("t01", "공룡 그림책", ("공룡",), True, "topic", ("children",), "tune"),
        TopicQuery("t02", "역사 입문서", ("역사",), False, "topic", ("history",), "tune"),
        TopicQuery("t03", "비 오는 날", ("비",), False, "mood", ("essay",), "tune"),
    ]
    seeds = [Seed("s01", "isbn:1", "tune"), Seed("s02", "isbn:2", "tune")]
    histories = [History("h01", ("isbn:2", "isbn:3", "acc:EX00004"), "tune")]
    items = {i.id: i for i in build_items(topics, seeds, histories, keys, children={1})}
    assert [items[x].group for x in ("t01", "t02", "t03")] == [
        Group.CHILDREN,
        Group.KEYWORD,
        Group.SITUATION,
    ]
    assert items["t02"].scenario.turns == ("역사 입문서",) and items["t02"].picks == ()
    assert items["s02"].picks == ("isbn:2",) and items["s02"].scenario.turns == (SIMILAR_TEXT,)
    assert items["h01"].picks == ("isbn:2", "isbn:3", "acc:EX00004")
    assert items["h01"].scenario.turns == (ANYTHING_TEXT,)
    assert items["h01"].group == Group.ANYTHING


def test_children_sentences() -> None:
    """[platform/conversation-recommendation-evals] 세트 항목을 대화로 / 어린이 기준 책"""
    keys = {"isbn:1": 1, "isbn:2": 2}
    seeds = [Seed("s01", "isbn:1", "tune")]
    histories = [History("h01", ("isbn:1",), "tune"), History("h02", ("isbn:1", "isbn:2"), "tune")]
    items = {i.id: i for i in build_items([], seeds, histories, keys, children={1})}
    assert items["s01"].scenario.turns == (SIMILAR_CHILDREN_TEXT,)
    assert items["h01"].scenario.turns == (ANYTHING_CHILDREN_TEXT,)
    assert items["h02"].scenario.turns == (ANYTHING_TEXT,)  # 섞인 기록은 일반 문장
    assert is_children_request([SIMILAR_CHILDREN_TEXT])
    assert is_children_request([ANYTHING_CHILDREN_TEXT])
    assert not is_children_request([SIMILAR_TEXT])
    assert not is_children_request([ANYTHING_TEXT])


async def _profile(catalog, capture: Capture):
    register_related_scope(children_related_scope)
    base = build_librarian_profiles((children_extension(),))[catalog.loan_mode]
    return capturing(base, capture)


async def test_history_session_books(
    session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[platform/conversation-recommendation-evals] 세트 항목을 대화로 / 최근 기록 항목"""
    catalog = await _load(session, tmp_path)
    keys = sorted(k for k, i in catalog.keys.items() if i not in catalog.children)[:3]
    [history] = build_items([], [], [History("h01", tuple(keys), "tune")], catalog.keys, set())
    profile = await _profile(catalog, Capture())
    seen: list[tuple[int, ...]] = []
    original = chat.session_books

    async def spy(s, library_id, session_id):
        books = await original(s, library_id, session_id)
        seen.append(books)
        return books

    monkeypatch.setattr(chat, "session_books", spy)
    llm = FakeLlm([turn(call("find_related_books", {"library_book_id": None})), submit("요")])
    picks = [catalog.keys[k] for k in history.picks]
    result = await run_scenario(
        session, llm, profile, catalog, history.scenario, _cached(tmp_path), picks=picks
    )
    assert len(llm.requests) == 2  # 고른 턴 셋은 LLM을 부르지 않았다
    assert seen[-1] == tuple(reversed(picks))  # 마지막 턴의 세션 책: 기록의 마지막 책이 먼저
    assert result.last.selected == tuple(picks)


# --- tool 입력과 결과는 평가 안에서만 ---


async def test_capture_two_searches_and_steps(session: AsyncSession, tmp_path: Path) -> None:
    """[platform/conversation-recommendation-evals] tool 입력과 결과는 평가 안에서만 / 낱말 받기

    [platform/conversation-recommendation-evals] tool 입력과 결과는 평가 안에서만 / 실행 기록 그대로
    """
    catalog = await _load(session, tmp_path)
    capture = Capture()
    profile = await _profile(catalog, capture)
    query = TopicQuery("t02", "역사 책", ("역사",), False, "topic", ("history",), "tune")
    [topic] = build_items([query], [], [], catalog.keys, catalog.children)
    llm = FakeLlm([search("대화", "평가"), search("작가1"), submit("없어요", suggest=True)])
    result = await run_scenario(session, llm, profile, catalog, topic.scenario, _cached(tmp_path))
    calls = capture.take()
    assert [c.keywords for c in calls] == [["대화", "평가"], ["작가1"]]
    assert calls[0].books and all(b in catalog.keys.values() for b in calls[0].books)
    steps = list(
        await session.scalars(
            select(AgentStep).where(
                AgentStep.run_id == result.last.run_id, AgentStep.kind == StepKind.TOOL
            )
        )
    )
    assert [s.name for s in steps] == ["search_collection", "search_collection"]
    assert all(s.detail is None for s in steps)  # 낱말은 실행 기록에 없다
    unwrapped = build_librarian_profiles((children_extension(),))[catalog.loan_mode]
    assert [t.record_fields for t in profile.tools] == [t.record_fields for t in unwrapped.tools]
    run = item_run(topic, result, calls, catalog.key_of)
    assert run.tool_top == [catalog.key_of[i] for i in calls[0].books[:5]]
    assert run.calls[0]["input"]["keywords"] == ["대화", "평가"]


async def test_similar_item_end_to_end(session: AsyncSession, tmp_path: Path) -> None:
    """[platform/conversation-recommendation-evals] 세트 항목을 대화로 / 비슷한 책 항목

    가짜 LLM으로 끝까지 돌고, 감싼 기록의 관련 책 결과가 다시 구한 결과와 같다.
    """
    catalog = await _load(session, tmp_path)
    capture = Capture()
    profile = await _profile(catalog, capture)
    base = min(i for i in catalog.recommendable if i not in catalog.children)
    seed_key = catalog.key_of[base]
    [similar] = build_items([], [Seed("s01", seed_key, "tune")], [], catalog.keys, catalog.children)
    other = min(i for i in catalog.recommendable if i not in catalog.children and i != base)
    llm = FakeLlm(
        [turn(call("find_related_books", {"library_book_id": base})), submit("이거요", other)]
    )
    result = await run_scenario(
        session, llm, profile, catalog, similar.scenario, _cached(tmp_path), picks=[base]
    )
    calls = capture.take()
    assert len(llm.requests) == 2
    assert [c.name for c in calls] == ["find_related_books"]
    assert tuple(dict.fromkeys(calls[0].books)) == result.last.related
    run = item_run(similar, result, calls, catalog.key_of)
    assert run.cards == [catalog.key_of[other]] and run.violations == {}


# --- 카드 채점 ---


def test_score_example() -> None:
    """[platform/conversation-recommendation-evals] 카드 채점 / 지표 계산"""
    labels = {"a": 2, "c": 2, "d": 1}
    score = score_keys(["a", "b", "x"], {**labels, "b": 0})
    assert score.hit == 1.0
    assert score.recall == pytest.approx(1 / 3)
    assert score.unlabeled == 1 and score.count == 3
    assert score.ndcg == pytest.approx(ndcg([2, 0, None], [2, 2, 1, 0]))


def test_score_no_cards() -> None:
    """[platform/conversation-recommendation-evals] 카드 채점 / 카드 없음"""
    score = score_keys([], {"a": 2})
    assert (score.hit, score.recall, score.ndcg, score.count) == (0.0, 0.0, 0.0, 0)
    [whole, *_] = group_rows([_run("t01", Group.KEYWORD, cards=[])], {"topic": {"t01": {"a": 2}}})
    assert whole.empty == 1


def test_score_tool_results() -> None:
    """[platform/conversation-recommendation-evals] 카드 채점 / tool 결과 채점"""
    run = _run("t01", Group.KEYWORD, cards=["b"], tool=[f"k{i}" for i in range(10)])
    [whole, *_] = group_rows([run], {"topic": {"t01": {"k0": 2, "b": 1}}})
    assert whole.tool.count == 5 and whole.tool.hit == 1.0
    assert whole.cards.hit == 0.0


def _run(item_id, group, cards=("a",), tool=(), set_name="topic", **extra) -> ItemRun:
    return ItemRun(set_name, item_id, group, list(cards), list(tool), **extra)


# --- 묶음별 요약 ---


def test_groups() -> None:
    """[platform/conversation-recommendation-evals] 묶음별 요약 / 묶음 나누기"""
    runs = [
        _run("t01", Group.CHILDREN),
        _run("t02", Group.SITUATION),
        _run("s01", Group.SIMILAR, set_name="similar"),
        _run("h01", Group.ANYTHING, set_name="history"),
    ]
    rows = {r.name: r.items for r in group_rows(runs, {"topic": {}, "similar": {}, "history": {}})}
    assert rows == {"전체": 4, "주제어": 0, "상황": 1, "어린이": 1, "비슷한 책": 1, "아무거나": 1}


def test_summary_not_pooled_and_cost() -> None:
    """[platform/conversation-recommendation-evals] 묶음별 요약 / 보충 전 표시"""
    calls = [
        {
            "name": "search_collection",
            "input": {"keywords": ["a"]},
            "books": [],
            "note": "n",
            "keyword_missing": True,
        },
    ]
    runs = [
        _run(
            "t01",
            Group.KEYWORD,
            cards=["a", "z"],
            calls=calls,
            input_tokens=1_000_000,
            output_tokens=100_000,
            llm_calls=2,
        )
    ]
    text = summary(
        runs, {"topic": {"t01": {"a": 2}}, "similar": {}, "history": {}}, ["머리"], "gpt-6-luna"
    )
    assert text.startswith(f"**{NOT_POOLED}**: 라벨 없는 카드 1권")
    assert "LLM 호출 2회" in text and "키워드 순위가 빈 검색 1번" in text
    assert "$0.1500" in text
    assert cost("gpt-6-luna", 1_000_000, 100_000) == Decimal("0.15")
    assert cost("unknown-model", 1, 1) is None
    labeled = summary(
        runs, {"topic": {"t01": {"a": 2, "z": 0}}, "similar": {}, "history": {}}, [], "gpt-6-luna"
    )
    assert NOT_POOLED not in labeled


# --- 규칙 위반 ---


def test_violation_fails() -> None:
    """[platform/conversation-recommendation-evals] 규칙 위반 / 위반으로 실패"""
    ok = _run("t01", Group.CHILDREN)
    bad = _run("t02", Group.CHILDREN, violations={"children_general": ["7"]})
    assert exit_code([ok]) == 0
    assert exit_code([ok, bad]) == 1
    text = summary([ok, bad], {"topic": {}, "similar": {}, "history": {}}, [], "gpt-6-luna")
    assert "규칙 위반 1건" in text and "topic/t02 children_general" in text


# --- 라벨 보충과 결과 형식 ---


def test_pool_targets(tmp_path: Path) -> None:
    """[platform/conversation-recommendation-evals] 라벨 보충과 결과 형식 / 보충 대상"""
    run = _run("t01", Group.KEYWORD, cards=["a", "b"], tool=["b", "c", "d"])
    other = _run("s01", Group.SIMILAR, cards=["e"], set_name="similar")
    folder = tmp_path / "run"
    folder.mkdir()
    for set_name, rows in results([run, other]).items():
        (folder / f"results-{set_name}.json").write_text(json.dumps(rows), encoding="utf-8")
    labels = Labels(tmp_path / "labels.json")
    labels.put("t01", "a", 2, "before")
    wanted = pool_keys(read_pool_results(folder, "topic"), ["chat"], labels)
    assert wanted == {"t01": ["b", "c", "d"]}
    assert read_pool_results(folder, "similar") == {"chat": {"s01": [{"key": "e"}]}}


# --- 실행 사이 비교 ---


def _saved(name: str, cards: list[str], hashes=None) -> SavedRun:
    meta = {"model": "m", "profile_version": "v6", "set_hashes": hashes or {"topic": "x"}}
    return SavedRun(name, meta, [_run("t01", Group.KEYWORD, cards=cards)])


def test_compare_uses_current_labels() -> None:
    """[platform/conversation-recommendation-evals] 실행 사이 비교 / 지금 라벨로"""
    first, second = _saved("a", ["new"]), _saved("b", ["old"])
    before = compare_runs(
        [first, second], {"topic": {"t01": {"old": 2}}, "similar": {}, "history": {}}
    )
    after = compare_runs(
        [first, second], {"topic": {"t01": {"old": 2, "new": 2}}, "similar": {}, "history": {}}
    )
    assert "| b | m | v6 | +1.000 | 1·0·0" in before
    assert "| b | m | v6 | +0.000 | 0·1·0" in after  # 첫 실행도 보충한 라벨로 다시 채점


def test_compare_set_mismatch(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """[platform/conversation-recommendation-evals] 실행 사이 비교 / 세트가 다름"""
    with pytest.raises(SetMismatchError):
        compare_runs([_saved("a", []), _saved("b", [], {"topic": "y"})], {"topic": {}})
    for name, hashes in (("a", {"topic": "x"}), ("b", {"topic": "y"})):
        folder = tmp_path / name
        folder.mkdir()
        meta = {"model": "m", "profile_version": "v6", "set_hashes": hashes}
        (folder / "items.json").write_text(json.dumps({"meta": meta, "items": []}), "utf-8")
    monkeypatch.setattr(conversation_compare, "current_labels", lambda: {})
    assert conversation_compare.main([str(tmp_path / "a"), str(tmp_path / "b")]) == 1
    assert not list(tmp_path.glob("*/compare-*.md"))


def test_item_run_requires_single_llm_turn() -> None:
    """세트 항목은 LLM 턴이 하나다(고른 턴은 LLM 없음)."""
    from evals.librarian.checks import ScenarioResult

    chat_item = ChatItem("topic", "t01", Group.KEYWORD, replace(_scenario_stub()))
    with pytest.raises(AssertionError):
        item_run(chat_item, ScenarioResult(chat_item.scenario, []), [], {})


def _scenario_stub():
    from evals.librarian.scenarios import Expect, Scenario

    return Scenario("t01", ("x",), Expect.ANY, children=False, traces=())
