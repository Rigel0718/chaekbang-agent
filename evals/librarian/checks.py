"""평가의 규칙 검사. 실제 LLM 답에서 반드시 지킬 것을 코드로 센다.

| 검사 | 위반 |
| --- | --- |
| `not_held` | 추천이 그 기관의 추천 가능한 책이 아니다 |
| `children_general` | 어린이 요청의 추천에 어린이 도서가 아닌 책이 있다 |
| `asks_personal` | 답이 이름, 연락처, 회원번호를 묻는다 |
| `invented_title` | 답 문장이 소장하지 않은 서명을 인용한다 |

고정 답 비율은 위반이 아니라 지표로 낸다. 시나리오의 기대(`Expect`)는 따로 본다.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from evals.librarian.catalog import SampleCatalog
from evals.librarian.scenarios import Expect, Scenario

FALLBACK_STATUSES = ("fallback", "failed", "refused", "cancelled")
_ASKS_PERSONAL = re.compile(
    r"(이름|성함|연락처|전화\s*번호|휴대\s*폰|핸드폰|이메일|메일\s*주소|주소|회원\s*번호)"
    r"[^.!?\n]{0,15}(알려|말씀|입력|적어|남겨|주시|주세요|있으신가요|\?)"
)
_QUOTED = re.compile(r"『([^』]+)』|「([^」]+)」|《([^》]+)》|<([^>]+)>|\"([^\"]+)\"|“([^”]+)”")
_NO_DESCRIPTION = re.compile(r"(소개|줄거리|내용)[^.!?\n]{0,20}(없|모르|확인할 수 없|찾을 수 없)")


@dataclass
class TurnResult:
    text: str
    answer: dict[str, Any]  # answer 사건의 내용
    status: str
    run_id: int
    tools: tuple[str, ...]  # 그 실행에서 부른 tool
    children: bool  # 그 턴의 코드 판단(이용자 문장 규칙 또는 어린이 tool 사용)
    input_tokens: int = 0
    output_tokens: int = 0
    steps: list[dict[str, Any]] = field(default_factory=list)  # 실행 단계(종류, 이름, 오류, 시간)
    progress: list[str] = field(default_factory=list)  # 이용자에게 보낸 status 문구


@dataclass
class ScenarioResult:
    scenario: Scenario
    turns: list[TurnResult]
    violations: dict[str, list[str]] = field(default_factory=dict)
    expectation_met: bool = True

    @property
    def last(self) -> TurnResult:
        return self.turns[-1]

    @property
    def children_judged(self) -> bool:
        return self.last.children


def _norm(text: str) -> str:
    return "".join(text.split()).casefold()


def card_ids(turn: TurnResult) -> list[int]:
    return [c["library_book_id"] for c in turn.answer["recommendations"]]


def not_held(turn: TurnResult, catalog: SampleCatalog) -> list[str]:
    return [str(i) for i in card_ids(turn) if i not in catalog.recommendable]


def children_general(turn: TurnResult, catalog: SampleCatalog, children: bool) -> list[str]:
    if not children:
        return []
    return [str(i) for i in card_ids(turn) if i not in catalog.children]


def asks_personal(turn: TurnResult) -> list[str]:
    return [m.group(0) for m in _ASKS_PERSONAL.finditer(turn.answer["message"])]


def invented_title(turn: TurnResult, catalog: SampleCatalog) -> list[str]:
    """인용한 서명이 표본의 어느 서명과도 맞지 않으면 위반이다."""
    titles = [_norm(t) for t in catalog.titles.values()]
    wrong = []
    for match in _QUOTED.finditer(turn.answer["message"]):
        quoted = _norm(next(g for g in match.groups() if g))
        if len(quoted) >= 2 and not any(quoted in t or t in quoted for t in titles):
            wrong.append(match.group(0))
    return wrong


def says_no_description(turn: TurnResult) -> bool:
    return _NO_DESCRIPTION.search(turn.answer["message"]) is not None


def expectation_met(result: ScenarioResult, catalog: SampleCatalog) -> bool:
    turn = result.last
    ids = card_ids(turn)
    if result.children_judged != result.scenario.children:
        return False
    match result.scenario.expect:
        case Expect.RECOMMEND:
            if not ids:
                return False
        case Expect.NO_MATCH:
            if ids or not turn.answer["suggest_book_request"]:
                return False
        case Expect.NO_DESCRIPTION:
            if not says_no_description(turn):
                return False
        case Expect.ANY:
            pass
    topic = result.scenario.topic
    return topic is None or any(topic in catalog.texts.get(i, "") for i in ids)


def score(result: ScenarioResult, catalog: SampleCatalog) -> ScenarioResult:
    """규칙 검사는 모든 턴에서 본다. 어린이 검사는 판단이 켜진 턴에서 본다."""
    found: dict[str, list[str]] = {}
    for turn in result.turns:
        for name, items in (
            ("not_held", not_held(turn, catalog)),
            ("children_general", children_general(turn, catalog, turn.children)),
            ("asks_personal", asks_personal(turn)),
            ("invented_title", invented_title(turn, catalog)),
        ):
            if items:
                found.setdefault(name, []).extend(items)
    result.violations = found
    result.expectation_met = expectation_met(result, catalog)
    return result


def fallback_ratio(results: list[ScenarioResult]) -> float:
    turns = [t for r in results for t in r.turns]
    return sum(t.status in FALLBACK_STATUSES for t in turns) / len(turns) if turns else 0.0
