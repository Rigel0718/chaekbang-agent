"""[platform/recommendation-experiments] 라벨 도구, 지표, 변형 실행과 재현.

가짜 인코더와 테스트 DB의 작은 장서로 돈다. 임베딩 서버와 실험 장서 파일이 필요 없다.
"""

import json
from dataclasses import replace
from pathlib import Path

import openai
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.official_embeddings import run_official_embedding
from app.library.recommendation.embeddings import run_library_embedding
from app.library.recommendation.ranking import Ranked
from app.library.recommendation.topic import TopicSettings, find_by_topic
from evals.recommendation.__main__ import EXIT_OK, EXIT_PRECONDITION, run_topic, stable
from evals.recommendation.cache import CachedEmbedder
from evals.recommendation.draft import DraftError, apply_draft, apply_pool_draft
from evals.recommendation.keys import library_keys
from evals.recommendation.label import (
    Card,
    label_item,
    label_list,
    pool_keys,
    related_candidates,
    topic_candidates,
)
from evals.recommendation.labels import BEFORE, POOL, Labels
from evals.recommendation.metrics import compare, score_query
from evals.recommendation.review import ReviewError, page_data, render_page, review_label
from evals.recommendation.sets import TopicQuery
from evals.recommendation.variants import DEEP, VARIANTS, Variant, run_variant
from tests.conftest import Tenant
from tests.embedding_helpers import FakeEmbedder
from tests.helpers import add_audience, add_held_book, make_isbn

_numbers = iter(range(830, 1000))


# --- 지표 ---


def test_metric_values() -> None:
    """[platform/recommendation-experiments] 지표 / 값 계산"""
    labels = {"a": 2, "b": 1, "c": 1, "d": 1, "e": 0}
    ranked = ["e", "a", "x1", "b", "x2", "x3", "c", "x4", "x5", "x6"]
    score = score_query(ranked, labels, {})
    assert score.recall == 0.75
    assert score.hit == 1
    # 2위에 라벨 2, 4위에 라벨 1: (3/log2(3) + 1/log2(5)) / 이상적 순위(2, 1, 1, 1, 0)
    ideal = 3 + 1 / 1.5849625007211562 + 1 / 2 + 1 / 2.321928094887362
    assert score.ndcg == pytest.approx((3 / 1.5849625007211562 + 1 / 2.321928094887362) / ideal)


def test_unlabeled_books_count_as_zero() -> None:
    """[platform/recommendation-experiments] 지표 / 라벨 없는 책"""
    labels = {"a": 2, "b": 1}
    score = score_query(["a", "x", "b", "y", "c"], {**labels, "c": 0}, {})
    assert score.unlabeled == 2
    assert score.ndcg == score_query(["a", "c", "b", "c", "c"], {**labels, "c": 0}, {}).ndcg
    groups = {"a": (["kim"], ["s"]), "b": (["kim"], []), "c": (["lee"], ["s"])}
    assert score_query(["a", "b", "c"], labels, groups).overlap == 2


def test_same_variant_is_all_ties() -> None:
    """[platform/recommendation-experiments] 짝 비교 / 같은 변형"""
    values = [0.2, 0.9, 0.5, 0.0]
    same = compare(values, list(values))
    assert (same.wins, same.ties, same.losses) == (0, 4, 0)
    assert (same.low, same.high, same.mean_diff) == (0.0, 0.0, 0.0)
    better = compare(values, [0.4, 0.9, 0.7, 0.1])
    assert (better.wins, better.ties, better.losses) == (3, 1, 0)
    assert better == compare(values, [0.4, 0.9, 0.7, 0.1])  # 고정 시드
    assert 0 <= better.low <= better.mean_diff <= better.high


# --- 라벨 도구 ---


def _cards(*keys: str) -> list[Card]:
    return [Card(key, f"서명 {key}", "저자", "분류", "서가", "소개") for key in keys]


def _answers(*values: str):
    queue = list(values)
    return lambda _prompt: queue.pop(0)


def test_label_tool_resumes(tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 라벨 도구 / 이어 하기"""
    path = tmp_path / "labels" / "topic.json"
    shown: list[str] = []
    done = label_item(
        Labels(path), "t01", "공룡 책", _cards("a", "b", "c"), BEFORE,
        ask=_answers("2", "", "q"), show=shown.append,
    )  # fmt: skip
    assert done is False
    stored = json.loads(path.read_text(encoding="utf-8"))
    assert stored == {
        "t01": {
            "a": {"grade": 2, "stage": "before", "by": "user"},
            "b": {"grade": 0, "stage": "before", "by": "user"},
        }
    }

    shown.clear()
    again = Labels(path)
    assert label_item(
        again, "t01", "공룡 책", _cards("a", "b", "c"), POOL, ask=_answers("1"), show=shown.append
    )
    assert "서명 c" in shown[0] and "서명 a" not in "".join(shown)
    assert again.grades("t01") == {"a": 2, "b": 0, "c": 1}
    assert again.stage_counts() == {"before": 2, "pool": 1}


def test_label_tool_asks_again_on_bad_answer(tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 라벨 도구 / 잘못된 답"""
    labels = Labels(tmp_path / "topic.json")
    shown: list[str] = []
    label_item(labels, "t01", "질의", _cards("a"), BEFORE, ask=_answers("3", "x", "1"),
               show=shown.append)  # fmt: skip
    assert labels.grades("t01") == {"a": 1}
    assert sum("0, 1, 2 중 하나" in line for line in shown) == 2
    with pytest.raises(ValueError):
        labels.put("t01", "b", 3, BEFORE)


def test_list_mode_records_picks_and_zeros(tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 라벨 도구 / 목록에서 고르기"""
    path = tmp_path / "labels" / "topic.json"
    shown: list[str] = []
    done = label_list(
        Labels(path), "t01", "공룡 책", _cards("a", "b", "c", "d", "e"), BEFORE,
        ask=_answers("1", "3, 4", ""), show=shown.append,
    )  # fmt: skip
    assert done is True
    assert Labels(path).grades("t01") == {"a": 2, "b": 0, "c": 1, "d": 1, "e": 0}
    assert Labels(path).stage_counts() == {"before": 5, "pool": 0}
    assert "  1. 서명 a / 저자 | 분류 | 서가" in shown[0] and "(5권)" in shown[0]
    assert any("나머지 2권은 0" in line for line in shown)


def test_list_mode_asks_again_on_bad_numbers(tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 라벨 도구 / 잘못된 번호"""
    path = tmp_path / "topic.json"
    labels = Labels(path)
    shown: list[str] = []
    answers = _answers("7", "x", "1", "1", "?2", "2", "", "r", "3", "", "")
    # 7 → 다시, x → 다시, 2인 1 / 1인 1 → 겹쳐 다시, ?2 → 카드 보기, 2인 2 / 1인 없음 → r 다시,
    # 2인 3 / 1인 없음 → 확인
    assert label_list(labels, "t01", "질의", _cards("a", "b", "c"), BEFORE,
                      ask=answers, show=shown.append)  # fmt: skip
    assert sum("1~3 사이의 번호" in line for line in shown) == 2
    assert sum("2와 1에 모두 든 번호" in line for line in shown) == 1
    assert any(line.startswith("\n2.\n") and "서명 b" in line for line in shown)
    assert labels.grades("t01") == {"a": 0, "b": 0, "c": 2}


def test_list_mode_quit_before_confirm_writes_nothing(tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 라벨 도구 / 확인하지 않고 끝내기"""
    path = tmp_path / "topic.json"
    shown: list[str] = []
    done = label_list(Labels(path), "t01", "질의", _cards("a", "b"), BEFORE,
                      ask=_answers("1", "", "q"), show=shown.append)  # fmt: skip
    assert done is False and not path.exists()

    shown.clear()
    again = Labels(path)
    assert label_list(again, "t01", "질의", _cards("a", "b"), BEFORE,
                      ask=_answers("", "2", ""), show=shown.append)  # fmt: skip
    assert "(2권)" in shown[0]
    assert again.grades("t01") == {"a": 0, "b": 1}
    # 다 단 항목은 묻지 않는다
    assert label_list(
        again, "t01", "질의", _cards("a", "b"), BEFORE, ask=_answers(), show=shown.append
    )


def test_draft_is_recorded_as_claude(tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 라벨 초안과 검수 / 초안 기록"""
    labels = Labels(tmp_path / "topic.json")
    assert apply_draft(labels, "t01", ["a", "b", "c"], {"a": 2}) == 3
    again = Labels(tmp_path / "topic.json")
    assert again.grades("t01") == {"a": 2, "b": 0, "c": 0}
    assert {again.labeler("t01", key) for key in "abc"} == {"claude"}
    assert again.stage_counts() == {"before": 3, "pool": 0}
    with pytest.raises(DraftError):
        apply_draft(labels, "t01", ["a", "b", "c"], {"z": 1})


def test_review_changes_grade_and_labeler(tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 라벨 초안과 검수 / 검수에서 고침"""
    labels = Labels(tmp_path / "topic.json")
    apply_draft(labels, "t01", ["a", "b"], {"a": 2})
    review_label(labels, "t01", "a", 1)
    again = Labels(tmp_path / "topic.json")
    assert again.grade("t01", "a") == 1
    assert (again.labeler("t01", "a"), again.stage("t01", "a")) == ("user", "before")
    assert again.labeler("t01", "b") == "claude"
    with pytest.raises(ReviewError):
        review_label(labels, "t01", "a", 5)
    data = page_data(again, [(_query("t01"), _cards("a", "b"))])
    assert [(b["key"], b["grade"], b["by"]) for b in data[0]["books"]] == [
        ("a", 1, "user"),
        ("b", 0, "claude"),
    ]
    assert "서명 a" in render_page(data)


def test_pool_draft_only_fills_unlabeled(tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 라벨 초안과 검수 / 보충 초안"""
    labels = Labels(tmp_path / "topic.json")
    labels.put("t01", "a", 2, BEFORE)
    assert apply_pool_draft(labels, "t01", ["b", "c"], {"b": 1}) == 2
    assert apply_pool_draft(labels, "t01", ["a", "b", "c"], {}) == 0
    assert labels.grades("t01") == {"a": 2, "b": 1, "c": 0}
    assert (labels.stage("t01", "a"), labels.stage("t01", "b")) == ("before", "pool")
    assert (labels.labeler("t01", "a"), labels.labeler("t01", "c")) == ("user", "claude")
    with pytest.raises(DraftError):
        apply_pool_draft(labels, "t01", ["b"], {"z": 1})


def test_draft_keeps_user_labels(tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 라벨 초안과 검수 / 사람 라벨은 덮지 않음"""
    labels = Labels(tmp_path / "topic.json")
    labels.put("t01", "a", 1, BEFORE)
    assert apply_draft(labels, "t01", ["a", "b"], {"b": 2}) == 1
    assert labels.grades("t01") == {"a": 1, "b": 2}
    assert (labels.labeler("t01", "a"), labels.labeler("t01", "b")) == ("user", "claude")
    assert labels.by_counts() == {"claude": 1, "user": 1}


async def _library(session: AsyncSession, library_id: int) -> dict[str, dict]:
    """어린이 3권, 일반 3권, 추천할 수 없는 책 1권. 이름 → 기관 도서."""
    books = {}
    for name in ("공룡 어린이책", "우주 어린이책", "바다 유아책"):
        books[name] = await add_held_book(
            session, library_id, isbn=make_isbn(next(_numbers)), title=name,
            official={"title": name, "description": f"{name} 소개"},
        )  # fmt: skip
        await add_audience(session, library_id, books[name]["id"])
    for name in ("공룡 일반서", "여행 수필집", "경제 입문서"):
        books[name] = await add_held_book(session, library_id, title=name, description=name)
    books["잃은 공룡책"] = await add_held_book(session, library_id, "lost", title="잃은 공룡책")
    return books


def _fields(keys: dict[str, int], books: dict[str, dict]) -> dict[str, str]:
    field_of = {
        "공룡 어린이책": "children", "우주 어린이책": "children", "바다 유아책": "toddler",
        "공룡 일반서": "science", "여행 수필집": "essay", "경제 입문서": "economy",
        "잃은 공룡책": "children",
    }  # fmt: skip
    by_id = {book["id"]: field_of[name] for name, book in books.items()}
    return {key: by_id[book_id] for key, book_id in keys.items()}


def _query(query_id: str, **changes) -> TopicQuery:
    base = {
        "text": "공룡이 나오는 책", "keywords": ("공룡",), "children": False, "style": "topic",
        "fields": ("science",), "split": "tune",
    }  # fmt: skip
    return TopicQuery(id=query_id, **{**base, **changes})


async def test_before_candidates_follow_fields_and_children(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[platform/recommendation-experiments] 실행 전 라벨 후보 / 분야와 어린이"""
    books = await _library(session, library_a.id)
    keys = await library_keys(session, library_a.id)
    fields = _fields(keys, books)
    query = _query("t01", children=True, fields=("toddler", "children"))
    ids = await topic_candidates(session, library_a.id, query, fields, keys)
    assert ids == sorted(
        books[name]["id"] for name in ("공룡 어린이책", "우주 어린이책", "바다 유아책")
    )
    general = _query("t02", fields=("science", "children"))
    ids = await topic_candidates(session, library_a.id, general, fields, keys)
    # 어린이 요청이 아니면 그 분야의 추천 가능한 책 전부(분실만 남은 책은 뺀다)
    assert books["공룡 일반서"]["id"] in ids and books["잃은 공룡책"]["id"] not in ids
    assert books["여행 수필집"]["id"] not in ids

    by_id = {book_id: key for key, book_id in keys.items()}
    base = by_id[books["공룡 어린이책"]["id"]]
    related = await related_candidates(session, library_a.id, [base], fields, keys)
    assert related == [books["우주 어린이책"]["id"]]


def test_pool_lists_only_unlabeled_books(tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 실행 뒤 라벨 보충 / 라벨 없는 책만"""
    labels = Labels(tmp_path / "topic.json")
    first = [f"k{n:02d}" for n in range(10)]
    second = [f"k{n:02d}" for n in range(5, 15)]
    for key in first + second[5:7]:
        labels.put("t01", key, 0, BEFORE)
    results = {
        "a": {"t01": [{"key": key} for key in first]},
        "b": {"t01": [{"key": key} for key in second]},
        "c": {"t01": [{"key": "다른 변형"}]},
    }
    assert pool_keys(results, ["a", "b"], labels) == {"t01": ["k12", "k13", "k14"]}
    labels.put("t01", "k12", 1, POOL)
    assert labels.stage_counts() == {"before": 12, "pool": 1}


# --- 실행 ---


async def _setup(session: AsyncSession, library_id: int, tmp_path: Path):
    books = await _library(session, library_id)
    embedder = FakeEmbedder()
    await run_official_embedding(session, embedder, full=True)
    await run_library_embedding(session, embedder, full=True, library_id=library_id)
    keys = await library_keys(session, library_id)
    by_id = {book_id: key for key, book_id in keys.items()}
    labels = Labels(tmp_path / "labels.json")
    labels.put("t01", by_id[books["공룡 일반서"]["id"]], 2, BEFORE)
    labels.put("t01", by_id[books["공룡 어린이책"]["id"]], 1, BEFORE)
    labels.put("t02", by_id[books["공룡 어린이책"]["id"]], 2, BEFORE)
    labels.put("t03", by_id[books["여행 수필집"]["id"]], 2, BEFORE)
    queries = [
        _query("t01"),
        _query("t02", children=True, fields=("children",)),
        _query("t03", text="가볍게 읽을 수필", keywords=("수필",), style="mood", split="check",
               fields=("essay",)),
    ]  # fmt: skip
    return books, embedder, labels, queries


async def _run(session, embedder, tmp_path, name, library_a, queries, labels, **options):
    options.setdefault("variant_names", ["current", "vec-text", "hybrid"])
    out = tmp_path / name
    code = await run_topic(
        session, CachedEmbedder(embedder, tmp_path / "vectors.json"), queries=queries,
        labels=labels, out=out, library_name=library_a.library["name"], **options,
    )  # fmt: skip
    return code, out


async def test_runs_without_llm(
    session: AsyncSession, library_a: Tenant, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[platform/recommendation-experiments] 변형 실행 / LLM 없이"""

    def refuse(*args, **kwargs):
        raise AssertionError("LLM을 부르면 안 된다")

    monkeypatch.setattr(openai, "AsyncOpenAI", refuse)
    _, embedder, labels, queries = await _setup(session, library_a.id, tmp_path)
    code, out = await _run(
        session, embedder, tmp_path, "run", library_a, queries, labels,
        variant_names=["current", "vec-text"],
    )  # fmt: skip
    assert code == EXIT_OK
    results = json.loads((out / "results.json").read_text(encoding="utf-8"))
    assert set(results) == {"current", "vec-text"}
    assert set(results["vec-text"]) == {"t01", "t02", "t03"}
    # `공룡 어린이책`(1)과 `공룡 일반서`(2)는 키워드 점수가 같아 서명 정렬 순서(가나다)로
    # 어린이책이 먼저다.
    assert [r["grade"] for r in results["current"]["t01"][:2]] == [1, 2]


async def test_unknown_variant(
    session: AsyncSession, library_a: Tenant, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """[platform/recommendation-experiments] 변형 실행 / 없는 변형"""
    _, embedder, labels, queries = await _setup(session, library_a.id, tmp_path)
    code, out = await _run(
        session, embedder, tmp_path, "run", library_a, queries, labels,
        variant_names=["current", "vec-banana"],
    )  # fmt: skip
    assert code == EXIT_PRECONDITION
    printed = capsys.readouterr().out
    assert "vec-banana" in printed and "hybrid-k60" in printed
    assert not out.exists()


async def test_experiment_library_missing(
    session: AsyncSession, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """[platform/recommendation-experiments] 변형 실행 / 실험 기관이 없음"""
    code = await run_topic(
        session, FakeEmbedder(), queries=[_query("t01")], labels=Labels(tmp_path / "l.json"),
        out=tmp_path / "run", variant_names=["current"],
    )  # fmt: skip
    assert code == EXIT_PRECONDITION
    assert "scripts/seed_experiment.py" in capsys.readouterr().out


async def test_missing_label_key_is_reported(
    session: AsyncSession, library_a: Tenant, tmp_path: Path
) -> None:
    """[platform/recommendation-experiments] 책 키 / 없는 키"""
    _, embedder, labels, queries = await _setup(session, library_a.id, tmp_path)
    labels.put("t01", "isbn:9799999999990", 2, BEFORE)
    code, out = await _run(session, embedder, tmp_path, "run", library_a, queries, labels)
    assert code == EXIT_OK
    assert "찾지 못한 키 1건" in (out / "summary.md").read_text(encoding="utf-8")


async def test_summary_counts_labels_by_labeler(
    session: AsyncSession, library_a: Tenant, tmp_path: Path
) -> None:
    """[platform/recommendation-experiments] 라벨 초안과 검수 / 단 쪽별 수"""
    _, embedder, _, queries = await _setup(session, library_a.id, tmp_path)
    keys = sorted(await library_keys(session, library_a.id))
    labels = Labels(tmp_path / "by.json")
    apply_draft(labels, "t01", keys[:2], {keys[0]: 2})
    labels.put("t02", keys[0], 1, BEFORE)
    code, out = await _run(session, embedder, tmp_path, "run", library_a, queries, labels)
    assert code == EXIT_OK
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "claude 2건" in summary and "user 1건" in summary


async def test_children_violation_fails_the_run(
    session: AsyncSession, library_a: Tenant, tmp_path: Path
) -> None:
    """[platform/recommendation-experiments] 규칙 위반 검사 / 어린이 위반"""
    books, embedder, labels, queries = await _setup(session, library_a.id, tmp_path)

    async def ignores_condition(session, embedder, library_id, query, within):
        return [Ranked(books["공룡 일반서"]["id"], 1.0), Ranked(books["잃은 공룡책"]["id"], 0.5)]

    variants = {
        **VARIANTS,
        "broken": Variant("broken", "조건을 무시한다", runner=ignores_condition),
    }
    code, out = await _run(
        session, embedder, tmp_path, "run", library_a, queries, labels,
        variant_names=["current", "broken"], variants=variants,
    )  # fmt: skip
    assert code == EXIT_PRECONDITION
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "어린이 요청의 일반 도서: 2건" in summary
    assert "추천할 수 없는 책: 3건" in summary

    code, out = await _run(session, embedder, tmp_path, "clean", library_a, queries, labels)
    assert code == EXIT_OK
    assert "어린이 요청의 일반 도서: 0건" in (out / "summary.md").read_text(encoding="utf-8")


async def test_tables_per_split(session: AsyncSession, library_a: Tenant, tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 짝 비교 / 묶음별"""
    _, embedder, labels, queries = await _setup(session, library_a.id, tmp_path)
    code, out = await _run(session, embedder, tmp_path, "run", library_a, queries, labels)
    summary = (out / "summary.md").read_text(encoding="utf-8")
    assert "## 조정 세트 (2개)" in summary and "## 확인 세트 (1개)" in summary
    assert "### 조정 · 어린이 (1개)" in summary and "### 확인 · 상황 (1개)" in summary
    assert "| current | 2 |" in summary and "| current | 1 |" in summary

    code, out = await _run(
        session, embedder, tmp_path, "tune", library_a, queries, labels, split="tune"
    )
    assert "확인 세트" not in (out / "summary.md").read_text(encoding="utf-8")


async def test_same_command_same_numbers(
    session: AsyncSession, library_a: Tenant, tmp_path: Path
) -> None:
    """[platform/recommendation-experiments] 결과 기록과 재현 / 두 번 실행"""
    _, embedder, labels, queries = await _setup(session, library_a.id, tmp_path)
    names = ["current", "vec-text", "hybrid", "series1", "mmr0.5"]
    fingerprint = ["- 평가 세트 해시: abc", "- 커밋: test"]
    summaries = []
    for name in ("first", "second"):
        code, out = await _run(
            session, embedder, tmp_path, name, library_a, queries, labels,
            variant_names=names, fingerprint=fingerprint,
        )  # fmt: skip
        assert code == EXIT_OK
        summaries.append((out / "summary.md").read_text(encoding="utf-8"))
    assert stable(summaries[0]) == stable(summaries[1])
    assert "평가 세트 해시: abc" in summaries[0] and "벡터 fake-model v2 full: 6" in summaries[0]
    assert "시각:" in summaries[0] and "시각:" not in stable(summaries[0])
    first = json.loads((tmp_path / "first" / "results.json").read_text(encoding="utf-8"))
    second = json.loads((tmp_path / "second" / "results.json").read_text(encoding="utf-8"))
    assert first == second


async def test_query_vectors_are_cached(
    session: AsyncSession, library_a: Tenant, tmp_path: Path
) -> None:
    """[platform/recommendation-experiments] 결과 기록과 재현 / 캐시"""
    _, embedder, labels, queries = await _setup(session, library_a.id, tmp_path)
    await _run(session, embedder, tmp_path, "first", library_a, queries, labels)
    assert sorted(text for call in embedder.query_calls for text in call) == [
        "가볍게 읽을 수필",
        "공룡이 나오는 책",
    ]
    embedder.query_calls.clear()
    code, _ = await _run(session, embedder, tmp_path, "second", library_a, queries, labels)
    assert code == EXIT_OK
    assert embedder.query_calls == []


async def test_label_change_changes_fingerprint(
    session: AsyncSession, library_a: Tenant, tmp_path: Path
) -> None:
    """[platform/recommendation-experiments] 결과 기록과 재현 / 라벨이 바뀜"""
    from evals.recommendation.sets import file_hash

    books, embedder, labels, queries = await _setup(session, library_a.id, tmp_path)
    before = file_hash(labels.path)
    keys = await library_keys(session, library_a.id)
    by_id = {book_id: key for key, book_id in keys.items()}
    labels.put("t01", by_id[books["공룡 일반서"]["id"]], 1, BEFORE)
    after = file_hash(labels.path)
    assert before != after and len(after) == 12
    code, out = await _run(
        session, embedder, tmp_path, "run", library_a, queries, labels,
        fingerprint=[f"- 라벨 해시: {after}"],
    )  # fmt: skip
    assert f"라벨 해시: {after}" in (out / "summary.md").read_text(encoding="utf-8")


# --- 합친 순위의 벡터 질의 입력 (add-topic-search-tool) ---


async def _topic_calls(session: AsyncSession, library_a: Tenant, tmp_path: Path, name: str):
    _, embedder, _, queries = await _setup(session, library_a.id, tmp_path)
    embedder.query_calls.clear()
    query = _query("t09", text="공룡이 나오는 책", keywords=("공룡", "화석"))
    ranked = await run_variant(session, embedder, VARIANTS[name], library_a.id, query, None)
    return [text for call in embedder.query_calls for text in call], ranked, embedder, query


async def test_keyword_input_variant(
    session: AsyncSession, library_a: Tenant, tmp_path: Path
) -> None:
    """[platform/recommendation-experiments] 합친 순위의 벡터 질의 입력 변형 / 낱말 입력 변형"""
    calls, _, _, _ = await _topic_calls(session, library_a, tmp_path, "hybrid-vkw")
    assert calls == ["공룡 화석"]


async def test_existing_hybrid_keeps_text_input(
    session: AsyncSession, library_a: Tenant, tmp_path: Path
) -> None:
    """[platform/recommendation-experiments] 합친 순위의 벡터 질의 입력 변형 / 기존 변형 고정"""
    for name in ("hybrid-k60", "hybrid", "best", "vec-text", "series1", "mmr0.7"):
        assert VARIANTS[name].settings.vector_input == "text", name
    calls, _, _, _ = await _topic_calls(session, library_a, tmp_path, "hybrid-k60")
    assert calls == ["공룡이 나오는 책"]


async def test_product_default_variant(
    session: AsyncSession, library_a: Tenant, tmp_path: Path
) -> None:
    """[platform/recommendation-experiments] 합친 순위의 벡터 질의 입력 변형 / 제품 기본 변형"""
    _, ranked, embedder, query = await _topic_calls(session, library_a, tmp_path, "hybrid-best")
    expected = await find_by_topic(
        session, embedder, library_id=library_a.id, text=query.text, keywords=query.keywords,
        settings=replace(TopicSettings(), limit=DEEP),
    )  # fmt: skip
    assert ranked == expected
