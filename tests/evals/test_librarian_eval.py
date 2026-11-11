"""AI 사서 평가의 규칙 검사와 시나리오 추적. 실제 LLM을 부르지 않는다."""

import re
from pathlib import Path

from evals.librarian.catalog import BookState, SampleCatalog
from evals.librarian.checks import (
    ScenarioResult,
    TurnResult,
    asks_personal,
    children_general,
    fallback_ratio,
    invented_title,
    not_held,
    says_no_description,
    score,
)
from evals.librarian.scenarios import SCENARIOS, Expect, Scenario

OPENSPEC = Path(__file__).resolve().parents[2] / "openspec"


def _spec_roots(openspec: Path = OPENSPEC) -> list[Path]:
    """현재 스펙과 archive되지 않은 change의 delta. 진행 중인 change의 평가 시나리오도 본다."""
    changes = sorted(
        p / "specs"
        for p in (openspec / "changes").iterdir()
        if p.is_dir() and p.name != "archive" and (p / "specs").is_dir()
    )
    return [openspec / "specs", *changes]


def _catalog() -> SampleCatalog:
    catalog = SampleCatalog(library_id=1, loan_mode="internal")
    catalog.states = {1: BookState.AVAILABLE, 2: BookState.ON_LOAN, 3: BookState.LOST_ONLY}
    catalog.titles = {1: "공룡 대탐험", 2: "우리 집 요리", 3: "잃어버린 책"}
    catalog.texts = {1: "공룡 대탐험\n공룡 이야기", 2: "우리 집 요리", 3: "잃어버린 책"}
    catalog.children = {1}
    return catalog


def _turn(message="추천해요", ids=(), suggest=False, status="completed", children=False):
    return TurnResult(
        text="질문",
        answer={
            "message": message,
            "recommendations": [{"library_book_id": i} for i in ids],
            "suggest_book_request": suggest,
        },
        status=status,
        run_id=1,
        tools=(),
        children=children,
    )


def test_not_held() -> None:
    assert not_held(_turn(ids=[1, 2]), _catalog()) == []
    assert not_held(_turn(ids=[3, 99]), _catalog()) == ["3", "99"]


def test_children_general() -> None:
    assert children_general(_turn(ids=[1, 2]), _catalog(), children=False) == []
    assert children_general(_turn(ids=[1, 2]), _catalog(), children=True) == ["2"]


def test_asks_personal() -> None:
    assert asks_personal(_turn("이 책을 추천해요. 서가에서 찾아보세요.")) == []
    assert asks_personal(_turn("성함과 연락처를 알려 주세요"))
    assert asks_personal(_turn("회원번호를 입력해 주세요"))


def test_invented_title() -> None:
    assert invented_title(_turn("『공룡 대탐험』을 추천해요"), _catalog()) == []
    assert invented_title(_turn("『공룡대탐험』 좋아요"), _catalog()) == []
    assert invented_title(_turn("『쥬라기 비밀 일기』도 있어요"), _catalog()) == [
        "『쥬라기 비밀 일기』"
    ]


def test_says_no_description() -> None:
    assert says_no_description(_turn("이 책은 소개 정보가 없어서 내용을 알려 드리기 어려워요."))
    assert not says_no_description(_turn("공룡이 나오는 모험 이야기예요."))
    # 2026-11-11 평가에서 놓친 답 (add-library-guide 7.3)
    assert says_no_description(
        _turn("이 책은 소개와 목차 정보가 등록되어 있지 않아 구체적인 내용을 확인하기 어렵습니다.")
    )
    assert says_no_description(_turn("줄거리는 알 수 없어요."))
    assert not says_no_description(_turn("내용이 어렵지 않아 아이와 읽기 좋아요."))


def test_score_and_expectation() -> None:
    scenario = Scenario(
        "s", ("7살 공룡 책",), Expect.RECOMMEND, children=True, traces=(), topic="공룡"
    )
    good = score(ScenarioResult(scenario, [_turn(ids=[1], children=True)]), _catalog())
    assert good.violations == {} and good.expectation_met
    bad = score(ScenarioResult(scenario, [_turn(ids=[2], children=True)]), _catalog())
    assert bad.violations == {"children_general": ["2"]}
    assert not bad.expectation_met  # 2번 책에는 공룡이 없다
    wrong_judgment = score(ScenarioResult(scenario, [_turn(ids=[1])]), _catalog())
    assert not wrong_judgment.expectation_met


def test_no_match_expectation() -> None:
    scenario = Scenario("s", ("없는 주제",), Expect.NO_MATCH, children=False, traces=())
    assert score(ScenarioResult(scenario, [_turn(suggest=True)]), _catalog()).expectation_met
    assert not score(ScenarioResult(scenario, [_turn(ids=[1])]), _catalog()).expectation_met


def test_fallback_ratio() -> None:
    scenario = Scenario("s", ("a", "b"), Expect.ANY, children=False, traces=())
    result = ScenarioResult(scenario, [_turn(status="fallback"), _turn()])
    assert fallback_ratio([result]) == 0.5


def _spec_scenarios(roots: list[Path]) -> tuple[set[str], set[str]]:
    """(모든 스펙 시나리오, 평가로 확인하는 시나리오).

    평가로 확인하는 시나리오: 요구사항 본문에 '평가로 확인'이나 시나리오에 '평가 시나리오'가 있다.
    """
    every: set[str] = set()
    by_eval_traces: set[str] = set()
    for root in roots:
        for path in root.rglob("spec.md"):
            capability = str(path.parent.relative_to(root))
            requirement, by_eval = None, False
            lines = path.read_text(encoding="utf-8").splitlines()
            for i, line in enumerate(lines):
                if line.startswith("### Requirement: "):
                    requirement = line.removeprefix("### Requirement: ")
                    body = []
                    for following in lines[i + 1 :]:
                        if following.startswith("#"):
                            break
                        body.append(following)
                    by_eval = "평가로 확인" in " ".join(body)
                elif line.startswith("#### Scenario: "):
                    name = line.removeprefix("#### Scenario: ")
                    trace = f"[{capability}] {requirement} / {name}"
                    every.add(trace)
                    block = " ".join(lines[i + 1 : i + 3])
                    if by_eval or re.search(r"평가 시나리오", block):
                        by_eval_traces.add(trace)
    return every, by_eval_traces


def _missing_traces(traces: set[str], roots: list[Path]) -> set[str]:
    every, _ = _spec_scenarios(roots)
    return traces - every


def test_scenarios_cover_eval_requirements() -> None:
    """현재 스펙과 진행 중인 change의 평가로 확인하는 시나리오가 모두 평가 시나리오에 있다."""
    _, expected = _spec_scenarios(_spec_roots())
    assert len(expected) >= 5
    covered = {trace for s in SCENARIOS for trace in s.traces}
    assert expected <= covered, expected - covered


def test_traces_exist_in_specs() -> None:
    """평가 시나리오가 적은 추적은 현재 스펙이나 진행 중인 change에 있는 시나리오다."""
    covered = {trace for s in SCENARIOS for trace in s.traces}
    assert _missing_traces(covered, _spec_roots()) == set()


def test_unknown_trace_fails(tmp_path: Path) -> None:
    """없는 스펙 시나리오를 적은 추적은 걸린다."""
    spec = tmp_path / "specs" / "agent" / "x" / "spec.md"
    spec.parent.mkdir(parents=True)
    spec.write_text(
        "### Requirement: 요구\n본문\n\n#### Scenario: 있음\n- **WHEN** a\n- **THEN** b\n",
        encoding="utf-8",
    )
    (tmp_path / "changes").mkdir()
    roots = _spec_roots(tmp_path)
    assert _missing_traces({"[agent/x] 요구 / 있음"}, roots) == set()
    assert _missing_traces({"[agent/x] 요구 / 없음"}, roots) == {"[agent/x] 요구 / 없음"}


def test_scenario_ids_unique() -> None:
    ids = [s.id for s in SCENARIOS]
    assert len(ids) == len(set(ids))
    # 실행 비용을 가늠하는 상한. 안내 시나리오 11개를 더해 23개다(add-library-guide)
    assert 10 <= len(SCENARIOS) <= 25
