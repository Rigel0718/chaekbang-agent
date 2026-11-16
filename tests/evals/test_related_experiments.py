"""[platform/recommendation-experiments] 비슷한 책·최근 기록 실행, 후보, 초안·검수, 고정 표본.

테스트 DB의 작은 장서와 가짜 인코더로 돈다. 비슷한 책과 최근 기록은 저장된 벡터만 써서, 적재 뒤에는
인코딩을 부르면 실패하는 인코더로 실행한다.
"""

from itertools import count
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.contributors import sync_contributors
from app.central.models import Book, ExternalSource
from app.central.official_embeddings import run_official_embedding
from app.library.recommendation.embeddings import run_library_embedding
from app.library.recommendation.ranking import Ranked
from evals.recommendation.__main__ import (
    EXIT_OK,
    EXIT_PRECONDITION,
    history_spec,
    run_set,
    similar_spec,
)
from evals.recommendation.draft import RelatedItem, apply_draft
from evals.recommendation.keys import library_keys
from evals.recommendation.label import Card, related_candidates
from evals.recommendation.labels import BEFORE, Labels
from evals.recommendation.review import page_data, render_page, review_label
from evals.recommendation.sample import pick_sample, sample_line, sample_stats
from evals.recommendation.sets import History, Seed
from evals.recommendation.variants import SIMILAR_VARIANTS, Variant
from tests.conftest import Tenant
from tests.embedding_helpers import FakeEmbedder
from tests.helpers import add_audience, add_held_book, make_isbn

_numbers = count(300)


class _LoadOnly(FakeEmbedder):
    """적재한 뒤에는 인코딩을 부르면 실패한다."""

    locked = False

    async def encode_queries(self, texts):
        raise AssertionError("질의를 인코딩하면 안 된다")

    async def encode_documents(self, texts):
        assert not self.locked, "문서를 인코딩하면 안 된다"
        return await super().encode_documents(texts)


async def _linked(session: AsyncSession, library_id: int, title: str, author: str, **official):
    book = await add_held_book(
        session,
        library_id,
        isbn=make_isbn(next(_numbers)),
        title=title,
        official={
            "title": title,
            "author": author,
            "description": f"{title} 소개",
            "external_source": ExternalSource.YES24.value,
            **official,
        },
    )
    await sync_contributors(
        session, await session.scalar(select(Book).where(Book.id == book["book_id"]))
    )
    return book["id"]


async def _setup(session: AsyncSession, library_id: int):
    """어린이 3권(둘은 같은 지은이), 일반 4권(둘은 같은 책의 판본). 이름 → 기관 도서 id."""
    ids = {
        "어린이 기준": await _linked(session, library_id, "공룡 어린이책", "김동화 글"),
        "어린이 같은 지은이": await _linked(session, library_id, "우주 어린이책", "김동화 글"),
        "어린이 다른 책": await _linked(session, library_id, "바다 유아책", "박그림 글"),
        "일반 같은 지은이": await _linked(session, library_id, "어른을 위한 동화", "김동화 저"),
        "일반 기준": await _linked(session, library_id, "여행 수필집", "이수필 저"),
        "일반 특별판": await _linked(session, library_id, "여행 수필집 (특별판)", "이수필 저"),
        "일반 다른 책": await _linked(session, library_id, "경제 입문서", "최경제 저"),
    }
    for name in ("어린이 기준", "어린이 같은 지은이", "어린이 다른 책"):
        await add_audience(session, library_id, ids[name])
    embedder = _LoadOnly()
    await run_official_embedding(session, embedder, full=True)
    await run_library_embedding(session, embedder, full=True, library_id=library_id)
    embedder.locked = True
    keys = await library_keys(session, library_id)
    key_of = {name: key for key, book_id in keys.items() for name, i in ids.items() if i == book_id}
    field_of = {
        "어린이 기준": "children", "어린이 같은 지은이": "children", "어린이 다른 책": "toddler",
        "일반 같은 지은이": "fiction", "일반 기준": "essay", "일반 특별판": "essay",
        "일반 다른 책": "economy",
    }  # fmt: skip
    fields = {key_of[name]: field for name, field in field_of.items()}
    return ids, embedder, keys, key_of, fields


def _seeds(key_of: dict[str, str]) -> list[Seed]:
    return [
        Seed("s01", key_of["어린이 기준"], "tune"),
        Seed("s02", key_of["일반 기준"], "tune"),
        Seed("s03", key_of["일반 다른 책"], "check"),
    ]


async def _run(session, embedder, tmp_path: Path, library_a: Tenant, spec, labels=None, **options):
    options.setdefault("variant_names", ["sim-vec", "sim-rrf"])
    out = tmp_path / "run"
    code = await run_set(
        session,
        embedder,
        spec=spec,
        labels=labels or Labels(tmp_path / "labels.json"),
        out=out,
        library_name=library_a.library["name"],
        **options,
    )
    summary = (out / "summary.md").read_text(encoding="utf-8") if out.exists() else ""
    return code, summary


async def test_similar_run_without_encoding(
    session: AsyncSession, library_a: Tenant, tmp_path: Path
) -> None:
    """[platform/recommendation-experiments] 변형 실행 / 비슷한 책 실행"""
    ids, embedder, _, key_of, _ = await _setup(session, library_a.id)
    labels = Labels(tmp_path / "labels.json")
    labels.put("s01", key_of["어린이 같은 지은이"], 2, BEFORE)
    code, summary = await _run(
        session, embedder, tmp_path, library_a, similar_spec(_seeds(key_of)[:2]), labels
    )
    assert code == EXIT_OK
    assert "# 추천 실험: 비슷한 책" in summary and "기준 책 2개" in summary
    assert "| sim-vec | 2 |" in summary and "| sim-rrf | 2 |" in summary
    assert "어린이 항목의 일반 도서: 0건" in summary
    import json

    results = json.loads((tmp_path / "run" / "results.json").read_text(encoding="utf-8"))
    assert set(results) == {"sim-vec", "sim-rrf"} and set(results["sim-rrf"]) == {"s01", "s02"}
    found = [row["key"] for row in results["sim-rrf"]["s01"]]
    # 어린이 기준 책: 어린이 도서만, 기준 책은 없다. 같은 지은이의 일반 도서도 나오지 않는다
    assert set(found) == {key_of["어린이 같은 지은이"], key_of["어린이 다른 책"]}
    assert found[0] == key_of["어린이 같은 지은이"]
    # 일반 기준 책: 특별판(다른 판본)은 없다
    assert key_of["일반 특별판"] not in [row["key"] for row in results["sim-rrf"]["s02"]]


async def test_children_seed_violation_fails_the_run(
    session: AsyncSession, library_a: Tenant, tmp_path: Path
) -> None:
    """[platform/recommendation-experiments] 변형 실행 / 어린이 기준 책"""
    ids, embedder, _, key_of, _ = await _setup(session, library_a.id)

    async def ignores_condition(session, embedder, library_id, item, within):
        return [Ranked(ids["일반 같은 지은이"], 1.0)]

    variants = {
        **SIMILAR_VARIANTS,
        "broken": Variant("broken", "조건 무시", runner=ignores_condition),
    }
    spec = similar_spec(_seeds(key_of))
    from dataclasses import replace

    code, summary = await _run(
        session,
        embedder,
        tmp_path,
        library_a,
        replace(spec, variants=variants),
        variant_names=["sim-vec", "broken"],
    )
    assert code == EXIT_PRECONDITION
    assert "어린이 항목의 일반 도서: 1건" in summary


async def test_variant_of_another_set(
    session: AsyncSession, library_a: Tenant, tmp_path: Path, capsys
) -> None:
    """[platform/recommendation-experiments] 변형 실행 / 다른 세트의 변형"""
    _, embedder, _, key_of, _ = await _setup(session, library_a.id)
    code, summary = await _run(
        session,
        embedder,
        tmp_path,
        library_a,
        similar_spec(_seeds(key_of)),
        variant_names=["hybrid-k60"],
    )
    assert code == EXIT_PRECONDITION and summary == ""
    printed = capsys.readouterr().out
    assert "없는 변형: hybrid-k60" in printed and "sim-vec" in printed
    assert "current" not in printed.split("쓸 수 있는 변형:")[1]


async def test_similar_groups_and_empty_signal(
    session: AsyncSession, library_a: Tenant, tmp_path: Path
) -> None:
    """[platform/recommendation-experiments] 짝 비교 / 비슷한 책 묶음

    [platform/recommendation-experiments] 신호 건수 보고 / 빈 신호
    """
    _, embedder, _, key_of, _ = await _setup(session, library_a.id)
    code, summary = await _run(
        session,
        embedder,
        tmp_path,
        library_a,
        similar_spec(_seeds(key_of)),
        variant_names=["sim-vec", "sim-best"],
        split="tune",
    )
    assert code == EXIT_OK
    # 조정 2권: 어린이 기준(같은 지은이 책이 있다), 일반 기준(다른 판본뿐이라도 지은이가 겹친다)
    assert "### 조정 · 관련 책 있음 (2개)" in summary
    assert "### 조정 · 어린이 (1개)" in summary and "### 조정 · 일반 (1개)" in summary
    assert "- 같은 KDC 세목: 0건 (항목 2개 중)" in summary
    assert "- 같은 저자: 1건 (항목 2개 중, 평균 1.0권)" in summary
    assert "- 벡터 이웃: 2건" in summary

    code, summary = await _run(
        session,
        embedder,
        tmp_path,
        library_a,
        similar_spec(_seeds(key_of)),
        variant_names=["sim-vec"],
    )
    assert "### 확인 · 관련 책 없음 (1개)" in summary and "### 조정 · 관련 책 있음 (2개)" in summary


async def test_history_run(session: AsyncSession, library_a: Tenant, tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 변형 실행 (최근 기록, 저장된 벡터만)"""
    ids, embedder, _, key_of, fields = await _setup(session, library_a.id)
    histories = [
        History("h01", (key_of["어린이 기준"], key_of["어린이 다른 책"]), "tune"),
        History("h02", (key_of["일반 기준"], key_of["일반 다른 책"]), "tune"),
        History("h03", (key_of["일반 기준"], key_of["일반 특별판"]), "check"),
    ]
    code, summary = await _run(
        session,
        embedder,
        tmp_path,
        library_a,
        history_spec(histories, fields),
        variant_names=["hist-mean", "hist-per-book"],
    )
    assert code == EXIT_OK
    assert "# 추천 실험: 최근 기록" in summary and "기록 3개" in summary
    assert "### 조정 · 어린이 (1개)" in summary and "### 조정 · 섞인 분야 (1개)" in summary
    assert "### 확인 · 같은 분야 (1개)" in summary
    assert "- 우리 도서관 인기: 0건 (항목 3개 중)" in summary


async def test_candidates_leave_out_other_editions(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[platform/recommendation-experiments] 실행 전 라벨 후보 / 기준 책의 다른 판본"""
    ids, _, keys, key_of, fields = await _setup(session, library_a.id)
    found = await related_candidates(session, library_a.id, [key_of["일반 기준"]], fields, keys)
    assert ids["일반 특별판"] not in found and ids["일반 기준"] not in found
    other = await related_candidates(session, library_a.id, [key_of["일반 특별판"]], fields, keys)
    assert other == []


async def test_candidates_of_children_seed(session: AsyncSession, library_a: Tenant) -> None:
    """[platform/recommendation-experiments] 실행 전 라벨 후보 / 어린이 기준 책의 후보"""
    ids, _, keys, key_of, fields = await _setup(session, library_a.id)
    found = await related_candidates(session, library_a.id, [key_of["어린이 기준"]], fields, keys)
    assert found == [ids["어린이 같은 지은이"]]
    assert ids["일반 같은 지은이"] not in found
    # 일반 기준 책이면 같은 지은이의 어린이 도서도 후보다
    general = await related_candidates(
        session, library_a.id, [key_of["일반 같은 지은이"]], fields, keys
    )
    assert set(general) == {ids["어린이 기준"], ids["어린이 같은 지은이"]}


def _card(key: str) -> Card:
    return Card(key, f"서명 {key}", "저자", "분류", "서가", f"{key}의 소개 전문")


def test_similar_draft_is_recorded(tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 세 세트의 초안과 검수 / 비슷한 책 초안"""
    labels = Labels(tmp_path / "similar.json")
    assert apply_draft(labels, "s01", ["a", "b", "c"], {"a": 2}) == 3
    again = Labels(tmp_path / "similar.json")
    assert [again.grade("s01", key) for key in "abc"] == [2, 0, 0]
    assert {again.labeler("s01", key) for key in "abc"} == {"claude"}


def test_history_review_page_shows_base_books(tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 세 세트의 초안과 검수 / 최근 기록 검수 화면"""
    labels = Labels(tmp_path / "history.json")
    apply_draft(labels, "h01", ["a", "b"], {"a": 1})
    item = RelatedItem("h01", "기록1 + 기록2", False, "tune", (_card("기록1"), _card("기록2")))
    data = page_data(labels, [(item, [_card("a"), _card("b")])])
    assert [base["title"] for base in data[0]["bases"]] == ["서명 기록1", "서명 기록2"]
    assert data[0]["bases"][1]["description"] == "기록2의 소개 전문"
    page = render_page(data)
    assert "기록1의 소개 전문" in page and "서명 a" in page
    assert page.index("item.bases") < page.index("for (const book of picked")  # 후보 위에 그린다


def _many_labels(tmp_path: Path) -> Labels:
    labels = Labels(tmp_path / "similar.json")
    for item in ("s01", "s02"):
        keys = [f"{item}-k{n:02d}" for n in range(30)]
        picks = {key: 2 if n < 6 else 1 for n, key in enumerate(keys) if n < 12}
        apply_draft(labels, item, keys, picks)
    return labels


def test_sample_is_fixed(tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 고정 표본 검수 / 같은 표본"""
    labels = _many_labels(tmp_path)
    first = pick_sample(labels, 9)
    assert first == pick_sample(Labels(tmp_path / "similar.json"), 9) and len(first) == 9
    # 사람이 표본의 라벨을 고쳐도 표본은 그대로다(초안 등급으로 나눈다)
    item_id, key = first[0]
    review_label(labels, item_id, key, (labels.grade(item_id, key) + 1) % 3)
    assert pick_sample(labels, 9) == first


def test_sample_is_even_across_grades(tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 고정 표본 검수 / 등급별로 고르게"""
    labels = _many_labels(tmp_path)
    grades = [labels.grade(item_id, key) for item_id, key in pick_sample(labels, 9)]
    assert sorted(grades) == [0, 0, 0, 1, 1, 1, 2, 2, 2]
    assert sorted(labels.grade(i, k) for i, k in pick_sample(labels, 10)).count(2) == 4
    # 한 등급이 모자라면 다른 등급이 채운다
    few = Labels(tmp_path / "few.json")
    apply_draft(few, "s01", ["a", "b", "c", "d", "e"], {"a": 2})
    assert len(pick_sample(few, 4)) == 4 and len(pick_sample(few, 9)) == 5


def test_sample_agreement(tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 고정 표본 검수 / 일치율"""
    labels = Labels(tmp_path / "similar.json")
    apply_draft(labels, "s01", ["a", "b", "c", "d"], {"a": 2, "b": 1})
    assert "표본 4건, 일치율 -" in sample_line(labels, 4) and "보지 않은 표본 4건" in sample_line(
        labels, 4
    )
    for key, grade in (("a", 2), ("b", 1), ("c", 0), ("d", 1)):  # d만 고친다(0 → 1)
        review_label(labels, "s01", key, grade)
    again = Labels(tmp_path / "similar.json")
    line = sample_line(again, 4)
    assert "표본 4건, 일치율 75%" in line and "보지 않은 표본 0건" in line
    assert sample_stats(again, 4)["per_grade"] == {0: [2, 1], 1: [1, 1], 2: [1, 1]}
    assert again.labeler("s01", "d") == "user" and again.items["s01"]["d"]["draft"] == 0
    sample = pick_sample(again, 4)
    data = page_data(
        again,
        [(RelatedItem("s01", "기준", False, "tune", ()), [_card(k) for k in "abcd"])],
        sample[:2],
    )
    assert data[0]["sample"] is True and len(data[0]["books"]) == 2


def test_supplement_only_sample(tmp_path: Path) -> None:
    """[platform/recommendation-experiments] 고정 표본 검수 (보충 라벨만: 백업에 없던 라벨)"""
    import json
    import shutil

    from evals.recommendation.sample import new_pairs

    labels = _many_labels(tmp_path)
    backup = tmp_path / "backup.json"
    shutil.copy(labels.path, backup)
    apply_draft(labels, "s03", [f"n{n}" for n in range(6)], {"n0": 2, "n1": 1})
    only = new_pairs(Labels(labels.path), backup)
    assert only == {("s03", f"n{n}") for n in range(6)}
    sample = pick_sample(Labels(labels.path), 3, only)
    assert {item for item, _ in sample} == {"s03"}
    assert sorted(labels.grade(i, k) for i, k in sample) == [0, 1, 2]
    assert sample == pick_sample(Labels(labels.path), 3, only)  # 늘 같다
    assert json.loads(backup.read_text(encoding="utf-8"))  # 백업은 그대로다
    assert new_pairs(labels, tmp_path / "없음.json") == {
        (i, k) for i, entries in labels.items.items() for k in entries
    }
