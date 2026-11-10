"""검색 평가의 질의 만들기와 지표. 표본 없이 작은 자료로 본다."""

from app.core.text import compact, jamo
from evals.catalog_search.metrics import Outcome, rank, summarize
from evals.catalog_search.queries import (
    Book,
    author_name,
    clean_title,
    make_queries,
    query_base,
    suggest_inputs,
    typo,
)

BOOKS = [
    Book(1, "데미안", "헤르만 헤세 저/전영애 역"),
    Book(2, "최소한의 한국사", "최태성"),
    Book(3, "진짜 진짜 재밌는 공룡 그림책 (완전판)", "라이브 편집부"),
]


def test_queries_are_deterministic() -> None:
    assert make_queries(BOOKS) == make_queries(BOOKS)


def test_query_kinds() -> None:
    kinds = {q.kind for q in make_queries(BOOKS)}
    assert {"exact", "spacing", "prefix", "author", "vowel", "final", "key"} <= kinds
    assert {"word", "suggest", "found", "unrelated"} <= kinds


def test_typo_changes_one_place() -> None:
    for kind in ("vowel", "final", "key"):
        wrong = typo("데미안", kind, "데미안")
        assert wrong is not None and wrong != "데미안"
        assert len(wrong) == 3
        assert sum(a != b for a, b in zip(wrong, "데미안", strict=True)) == 1
    assert typo("ABC", "vowel", "ABC") is None


def test_helpers() -> None:
    assert clean_title("공룡 그림책 (완전판)") == "공룡 그림책"
    assert clean_title("[예스리커버] 아는 만큼 보인다") == "아는 만큼 보인다"
    assert query_base("데미안") == "데미안"
    assert query_base("은하수를 여행하는 히치하이커를 위한 안내서") == "은하수를"
    assert author_name("앤디 위어 저/박아람 역") == "앤디 위어"
    assert author_name("최태성") == "최태성"
    assert suggest_inputs("데미안") == ["데ㅁ", "데미ㅇ", "데미안"]
    assert jamo("데미안").startswith(jamo(suggest_inputs("데미안")[1]))


def test_spacing_query() -> None:
    spacing = [q.text for q in make_queries(BOOKS) if q.kind == "spacing"]
    assert "최소한의한국사" in spacing
    assert compact(spacing[0]) == compact("데미안")


def test_metrics() -> None:
    outcomes = [
        Outcome("exact", "a", 1, (1, 2)),
        Outcome("exact", "b", 2, (1, 3, 4, 5, 6, 2)),
        Outcome("exact", "c", 3, ()),
        Outcome("unrelated", "d", None, (7,)),
        Outcome("unrelated", "e", None, ()),
    ]
    assert rank(2, (1, 2)) == 2 and rank(9, (1,)) is None and rank(None, (1,)) is None
    scores = {s.kind: s for s in summarize(outcomes)}
    exact = scores["exact"]
    assert (exact.count, exact.hit1, exact.found) == (3, 1 / 3, 2 / 3)
    assert exact.hit5 == 1 / 3  # 6위는 5위 안이 아니다
    assert abs(exact.mrr - (1 + 1 / 6) / 3) < 1e-9
    assert scores["unrelated"].any_rate == 0.5
