"""[platform/recommendation-experiments] 대출 신호 파일, 신호 건수와 소장 겹침, 남겨 둔 분야 세트.

`add-loan-signals`. 테스트 DB의 작은 장서와 가짜 인코더로 돌고 외부 호출이 없다.
"""

import argparse
import json
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from evals.recommendation import __main__ as main_module
from evals.recommendation import labels as labels_module
from evals.recommendation.__main__ import EXIT_OK, EXIT_PRECONDITION, similar_spec
from evals.recommendation.labels import labels_file
from evals.recommendation.pick import BookInfo, pick_holdout
from evals.recommendation.sets import SetError, parse_seeds, parse_topic
from evals.recommendation.signals import FETCH_COMMAND, FileLoanSignals
from evals.recommendation.variants import (
    HISTORY_VARIANTS,
    HOLDOUT_VARIANTS,
    SIMILAR_VARIANTS,
    needs_loans,
)
from tests.conftest import Tenant
from tests.evals.test_recommendation_sets import FIELDS, _query
from tests.evals.test_related_experiments import _run, _seeds, _setup
from tests.helpers import make_isbn


def _args(**changes) -> argparse.Namespace:
    base = {
        "set": "similar",
        "variants": "",
        "split": "all",
        "reference": None,
        "holdout": False,
        "loan_signals": Path("/nonexistent/loan_signals.json"),
    }
    return argparse.Namespace(**{**base, **changes})


@pytest.fixture
def offline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN201
    """run()이 DB 없이 run_set 앞까지 돌게 한다. run_set에 넘어간 값을 모은다."""
    monkeypatch.setattr(labels_module, "LABELS_DIR", tmp_path / "labels")
    (tmp_path / "labels").mkdir()
    for name in ("similar.json", "holdout-similar.json"):
        (tmp_path / "labels" / name).write_text("{}", encoding="utf-8")
    fields = {"isbn:9791100000011": "children", "isbn:9791100000035": "religion"}
    monkeypatch.setattr(main_module, "load_fields", lambda path: fields)
    seeds = tmp_path / "seeds.json"
    seeds.write_text(
        json.dumps({"similar": [{"id": "s01", "book": "isbn:9791100000011", "split": "tune"}]}),
        encoding="utf-8",
    )
    holdout = tmp_path / "seeds-holdout.json"
    holdout.write_text(
        json.dumps({"similar": [{"id": "hs01", "book": "isbn:9791100000035", "split": "check"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(main_module, "SEEDS_FILE", seeds)
    monkeypatch.setattr(main_module, "HOLDOUT_SEEDS_FILE", holdout)
    calls: list[dict] = []

    async def fake_run_set(session, embedder, **options):  # noqa: ANN001, ANN202
        calls.append(options)
        return EXIT_OK

    monkeypatch.setattr(main_module, "run_set", fake_run_set)
    return calls


# --- 대출 신호 파일 ---


async def test_missing_loan_file(offline, capsys: pytest.CaptureFixture[str]) -> None:
    """[platform/recommendation-experiments] 대출 신호 파일 / 파일 없음"""
    assert await main_module.run(_args(variants="sim-vec,sim-best-co")) == EXIT_PRECONDITION
    assert FETCH_COMMAND in capsys.readouterr().err
    assert offline == []


async def test_variant_without_loans(offline) -> None:
    """[platform/recommendation-experiments] 대출 신호 파일 / 쓰지 않는 변형"""
    assert await main_module.run(_args(variants="sim-vec,sim-rrf")) == EXIT_OK
    (options,) = offline
    assert options["loan_signals"] is None
    assert not needs_loans(SIMILAR_VARIANTS["sim-vec"])
    assert needs_loans(SIMILAR_VARIANTS["sim-best-co"])
    assert needs_loans(HISTORY_VARIANTS["hist-mean-co"])
    assert not needs_loans(HISTORY_VARIANTS["hist-mean-rules"])


def _loan_file(usage: dict, popular: dict | None = None) -> FileLoanSignals:
    return FileLoanSignals({"fetched_on": "2026-11-18", "usage": usage, "popular": popular or {}})


async def test_pending_isbn_is_reported(
    session: AsyncSession, library_a: Tenant, tmp_path: Path
) -> None:
    """[platform/recommendation-experiments] 대출 신호 파일 / 받지 않은 ISBN"""
    ids, embedder, keys, key_of, _ = await _setup(session, library_a.id)
    seeds = _seeds(key_of)
    isbn = {seed.id: seed.book.removeprefix("isbn:") for seed in seeds}
    loans = _loan_file(
        {
            isbn["s01"]: None,
            isbn["s02"]: {"status": "found", "co_loans": [], "mania": [], "reader": []},
            isbn["s03"]: {"status": "found", "co_loans": [], "mania": [], "reader": []},
        }
    )
    code, summary = await _run(
        session,
        embedder,
        tmp_path,
        library_a,
        similar_spec(seeds),
        variant_names=["sim-vec", "sim-best-co"],
        loan_signals=loans,
    )
    assert code == EXIT_OK
    assert "받지 않은 ISBN 1건" in summary


async def test_overlap_lines(session: AsyncSession, library_a: Tenant, tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 신호 건수 보고 / 소장 겹침"""
    ids, embedder, keys, key_of, _ = await _setup(session, library_a.id)
    seeds = _seeds(key_of)[:2]
    child, general = (seed.book.removeprefix("isbn:") for seed in seeds)
    held = [
        key_of[name].removeprefix("isbn:")
        for name in ("어린이 같은 지은이", "일반 다른 책", "어린이 다른 책")
    ]
    strangers = [make_isbn(n) for n in range(880, 897)]
    loans = _loan_file(
        {
            child: {"status": "found", "co_loans": strangers[:10], "mania": [], "reader": []},
            general: {
                "status": "found",
                "co_loans": [*held, *strangers[10:17]],
                "mania": [],
                "reader": [],
            },
        },
        {"all-365": {"start": "a", "end": "b", "isbns": [held[1], strangers[0]]}},
    )
    code, summary = await _run(
        session,
        embedder,
        tmp_path,
        library_a,
        similar_spec(seeds),
        variant_names=["sim-vec", "sim-best-co"],
        loan_signals=loans,
    )
    assert code == EXIT_OK
    assert "- 함께 대출: 1건 (항목 2개 중, 평균 3.0권)" in summary
    assert "- 함께 대출 순위: 길이 합 20, 실험 기관이 가진 책 3권, 추천 가능 3권" in summary
    assert "- 정보나루 인기 `all-365`: 길이 2, 가진 책 1권, 추천 가능 1권" in summary
    assert "- 같은 KDC 세 자리: 0건" in summary
    results = json.loads((tmp_path / "run" / "results.json").read_text(encoding="utf-8"))
    ranks = [row["ranks"] for row in results["sim-best-co"]["s02"]]
    assert any("co_loan" in rank for rank in ranks)
    assert all("co_loan" not in row["ranks"] for row in results["sim-vec"]["s02"])


async def test_file_loan_signals_reads_period() -> None:
    """[platform/recommendation-experiments] 대출 신호 파일 (인기는 정한 기간의 목록)"""
    loans = FileLoanSignals(
        {
            "usage": {"a": {"status": "found", "co_loans": ["b"], "mania": ["c"], "reader": []}},
            "popular": {"all-365": {"isbns": ["x"]}, "all-90": {"isbns": ["y"]}, "teen-90": None},
        },
        popular_days=90,
    )
    assert await loans.co_loans("a") == ["b"]
    assert await loans.co_loans("a", "mania") == ["c"]
    assert await loans.co_loans("missing") == []
    assert await loans.popular("all") == ["y"]
    assert loans.popular_conditions() == {"all-365": ["x"], "all-90": ["y"]}


def test_best_variants_unchanged() -> None:
    """[platform/recommendation-experiments] 변형 실행 (채택 설정은 이번 단계 전과 같다)"""
    assert SIMILAR_VARIANTS["sim-best"].settings == SIMILAR_VARIANTS["sim-rrf"].settings
    assert SIMILAR_VARIANTS["sim-best-kdc0"].settings == SIMILAR_VARIANTS["sim-rrf-kdc0"].settings
    assert HISTORY_VARIANTS["hist-best"].settings == HISTORY_VARIANTS["hist-mean"].settings


# --- 남겨 둔 분야 세트 ---


async def test_holdout_reads_its_own_files(offline, tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 남겨 둔 분야 세트 / 따로 읽기"""
    assert await main_module.run(_args(holdout=True)) == EXIT_OK
    (options,) = offline
    assert options["labels"].path == tmp_path / "labels" / "holdout-similar.json"
    assert "(남겨 둔 분야 세트)" in options["fingerprint"][0]
    assert options["variant_names"] == list(HOLDOUT_VARIANTS["similar"])
    assert options["spec"].variants is SIMILAR_VARIANTS
    assert labels_file("topic", holdout=True).name == "holdout-topic.json"


async def test_holdout_unknown_variant(offline, capsys: pytest.CaptureFixture[str]) -> None:
    """[platform/recommendation-experiments] 남겨 둔 분야 세트 / 정해 두지 않은 변형"""
    code = await main_module.run(_args(holdout=True, variants="sim-vec,sim-rrf-kdc3"))
    assert code == EXIT_PRECONDITION
    printed = capsys.readouterr().out
    assert "sim-rrf-kdc3" in printed and "sim-vec, sim-rrf, sim-best" in printed
    assert offline == []


def test_holdout_tune_item_is_rejected() -> None:
    """[platform/recommendation-experiments] 남겨 둔 분야 세트 / 조정 항목"""
    with pytest.raises(SetError) as caught:
        parse_seeds(
            {"similar": [{"id": "hs01", "book": "isbn:9791100000035", "split": "tune"}]},
            FIELDS,
            holdout=True,
        )
    assert caught.value.item_id == "hs01"
    with pytest.raises(SetError, match="확인 세트"):
        parse_topic({"queries": [_query(id="ht01", fields=["religion"])]}, holdout=True)


def test_holdout_query_needs_holdout_field() -> None:
    """[platform/recommendation-experiments] 남겨 둔 분야 제외 / 남겨 둔 분야 세트의 다른 분야 질의

    (기준 책도 남겨 둔 분야여야 한다)
    """
    with pytest.raises(SetError) as caught:
        parse_topic(
            {"queries": [_query(id="ht02", fields=["fiction"], split="check")]}, holdout=True
        )
    assert caught.value.item_id == "ht02" and "남겨 둔 분야가 없다" in str(caught.value)
    (query,) = parse_topic(
        {"queries": [_query(id="ht03", fields=["health", "home"], split="check")]}, holdout=True
    )
    assert query.fields == ("health", "home")
    with pytest.raises(SetError, match="`fiction` 분야"):
        parse_seeds(
            {"similar": [{"id": "hs02", "book": "isbn:9791100000028", "split": "check"}]},
            FIELDS,
            holdout=True,
        )


def test_holdout_mixed_history() -> None:
    """[platform/recommendation-experiments] 남겨 둔 분야 제외 / 남겨 둔 분야 세트의 섞인 기록"""
    fields = {**FIELDS, "isbn:9791100000042": "travel"}
    _, histories = parse_seeds(
        {
            "history": [
                {
                    "id": "hh01",
                    "books": ["isbn:9791100000042", "isbn:9791100000028"],
                    "split": "check",
                }
            ]
        },
        fields,
        holdout=True,
    )
    assert histories[0].books == ("isbn:9791100000042", "isbn:9791100000028")
    with pytest.raises(SetError, match="남겨 둔 분야의 책이 없다"):
        parse_seeds(
            {"history": [{"id": "hh02", "books": ["isbn:9791100000028"], "split": "check"}]},
            fields,
            holdout=True,
        )


def test_pick_holdout() -> None:
    """[platform/recommendation-experiments] 남겨 둔 분야 세트 (기준 책·기록 고르기)"""
    books = []
    for field in ("religion", "art", "health", "travel", "fiction"):
        for n in range(6):
            key = f"acc:EX{len(books):05d}" if n == 5 else f"isbn:{make_isbn(len(books) + 1)}"
            books.append(BookInfo(key, field, children=False, related=n % 2 == 0))
    document = pick_holdout(books)
    assert document == pick_holdout(list(reversed(books)))
    similar, history = document["similar"], document["history"]
    by_key = {b.key: b for b in books}
    assert len(similar) == 8
    assert all(row["split"] == "check" for row in similar + history)
    seed_fields = [by_key[row["book"]].field for row in similar]
    assert sorted(seed_fields) == sorted(["religion", "art", "health", "travel"] * 2)
    assert any(row["book"].startswith("acc:") for row in similar)
    assert len(history) == 4
    mixed = history[-1]["books"]
    assert {by_key[key].field in {"religion", "art", "health", "travel"} for key in mixed} == {
        True,
        False,
    }
    used = [row["book"] for row in similar] + [k for row in history for k in row["books"]]
    assert len(used) == len(set(used))
    fields = {b.key: b.field for b in books}
    parse_seeds(document, fields, holdout=True)
