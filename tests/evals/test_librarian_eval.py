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

CHANGE = Path(__file__).resolve().parents[2] / "openspec" / "changes" / "add-librarian-agent"


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


def _eval_traces() -> set[str]:
    """delta 스펙에서 평가로 확인하는 시나리오 (요구사항이 '평가로 확인'이거나 '평가 시나리오')."""
    traces: set[str] = set()
    for path in (CHANGE / "specs").rglob("spec.md"):
        capability = str(path.parent.relative_to(CHANGE / "specs"))
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
                block = " ".join(lines[i + 1 : i + 3])
                if by_eval or re.search(r"평가 시나리오", block):
                    traces.add(f"[{capability}] {requirement} / {name}")
    return traces


def test_scenarios_cover_eval_requirements() -> None:
    """이번 change에서 평가로 확인하는 시나리오가 모두 평가 시나리오에 적혀 있다."""
    expected = _eval_traces()
    assert len(expected) >= 5
    covered = {trace for s in SCENARIOS for trace in s.traces}
    assert expected <= covered, expected - covered


def test_scenario_ids_unique() -> None:
    ids = [s.id for s in SCENARIOS]
    assert len(ids) == len(set(ids))
    assert 10 <= len(SCENARIOS) <= 14
