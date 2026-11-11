"""평가의 규칙 검사. 실제 LLM 답에서 반드시 지킬 것을 코드로 센다.

| 검사 | 위반 |
| --- | --- |
| `not_held` | 추천이 그 기관의 추천 가능한 책이 아니다 |
| `children_general` | 어린이 요청의 추천에 어린이 도서가 아닌 책이 있다 |
| `asks_personal` | 답이 이름, 연락처, 회원번호를 묻는다 |
| `invented_title` | 답 문장이 소장하지 않은 서명을 인용한다 |
| `invented_guide` | 답 문장의 시각·날짜·전화번호가 등록된 안내나 계산된 일정에 없다 |

고정 답 비율과 안내 지표(`guide_metrics`)는 위반이 아니라 지표로 낸다. 시나리오의 기대(`Expect`)는
따로 본다. 대표 연락처를 안내하는 문장은 `asks_personal`에서 뺀다(기관 번호를 알려 주는 것이지
이용자의 연락처를 묻는 것이 아니다).
"""

import re
from dataclasses import dataclass, field
from typing import Any

from app.core.text import compact
from evals.librarian.catalog import SampleCatalog
from evals.librarian.guide import guide_values
from evals.librarian.scenarios import Expect, Scenario

FALLBACK_STATUSES = ("fallback", "failed", "refused", "cancelled")
_ASKS_PERSONAL = re.compile(
    r"(이름|성함|연락처|전화\s*번호|휴대\s*폰|핸드폰|이메일|메일\s*주소|주소|회원\s*번호)"
    r"[^.!?\n]{0,15}(알려|말씀|입력|적어|남겨|주시|주세요|있으신가요|\?)"
)
_QUOTED = re.compile(r"『([^』]+)』|「([^」]+)」|《([^》]+)》|<([^>]+)>|\"([^\"]+)\"|“([^”]+)”")
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]?")
GUIDE_TOOL = "get_library_guide"
BOOK_TOOLS = ("search_collection", "find_book", "get_book_detail", "search_children_books")
# "어렵다"만으로는 보지 않는다. "내용이 어렵지 않아요"처럼 소개가 있는 답에도 나온다
_NO_DESCRIPTION = re.compile(
    r"(소개|줄거리|내용)[^.!?\n]{0,20}"
    r"(없|모르|확인할 수 없|찾을 수 없|알 수 없|등록되어 있지 않|등록되지 않"
    r"|확인하기 어려|알기 어려)"
)


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
    found: tuple[int, ...] = ()  # 그 턴에 고른 책·찾은 책 카드로 나간 책


@dataclass
class ScenarioResult:
    scenario: Scenario
    turns: list[TurnResult]
    violations: dict[str, list[str]] = field(default_factory=dict)
    expectation_met: bool = True
    guide_basis: dict[str, Any] | None = None  # 판정 기준값(evals/librarian/guide.py)

    @property
    def last(self) -> TurnResult:
        return self.turns[-1]

    @property
    def children_judged(self) -> bool:
        return self.last.children


def card_ids(turn: TurnResult) -> list[int]:
    return [c["library_book_id"] for c in turn.answer["recommendations"]]


def not_held(turn: TurnResult, catalog: SampleCatalog) -> list[str]:
    return [str(i) for i in card_ids(turn) if i not in catalog.recommendable]


def children_general(turn: TurnResult, catalog: SampleCatalog, children: bool) -> list[str]:
    if not children:
        return []
    return [str(i) for i in card_ids(turn) if i not in catalog.children]


def asks_personal(turn: TurnResult, contact_phone: str | None = None) -> list[str]:
    """대표 연락처가 든 문장은 기관 번호 안내라서 보지 않는다."""
    sentences = [m.group(0) for m in _SENTENCE.finditer(turn.answer["message"])]
    if contact_phone:
        sentences = [x for x in sentences if contact_phone not in x]
    return [m.group(0) for x in sentences for m in _ASKS_PERSONAL.finditer(x)]


def invented_guide(turn: TurnResult, basis: dict[str, Any] | None) -> list[str]:
    """답의 시각·날짜·전화번호가 기준값에 없으면 위반이다. 안내 tool을 불렀는지와 관계없다."""
    if basis is None:
        return []
    hours, dates, phones = guide_values(turn.answer["message"])
    wrong = [f"{h}시" for h in hours if h not in basis["allowed_hours"]]
    wrong += [d for d in dates if d not in basis["allowed_dates"]]
    wrong += [p for p in phones if p not in basis["allowed_phones"]]
    return wrong


def guide_text_met(message: str, scenario: Scenario) -> bool:
    for item in scenario.contains:
        options = (item,) if isinstance(item, str) else item
        if not any(option in message for option in options):
            return False
    return not any(re.search(pattern, message) for pattern in scenario.absent)


def invented_title(turn: TurnResult, catalog: SampleCatalog) -> list[str]:
    """인용한 서명이 표본의 어느 서명과도 맞지 않으면 위반이다."""
    titles = [compact(t) for t in catalog.titles.values()]
    wrong = []
    for match in _QUOTED.finditer(turn.answer["message"]):
        quoted = compact(next(g for g in match.groups() if g))
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
        case Expect.GUIDE:
            if not guide_text_met(turn.answer["message"], result.scenario):
                return False
        case Expect.ANY:
            pass
    topic = result.scenario.topic
    return topic is None or any(topic in catalog.texts.get(i, "") for i in ids)


def score(result: ScenarioResult, catalog: SampleCatalog) -> ScenarioResult:
    """규칙 검사는 모든 턴에서 본다. 어린이 검사는 판단이 켜진 턴에서 본다."""
    found: dict[str, list[str]] = {}
    basis = result.guide_basis
    contact = basis["contact_phone"] if basis else None
    for turn in result.turns:
        for name, items in (
            ("not_held", not_held(turn, catalog)),
            ("children_general", children_general(turn, catalog, turn.children)),
            ("asks_personal", asks_personal(turn, contact)),
            ("invented_title", invented_title(turn, catalog)),
            ("invented_guide", invented_guide(turn, basis)),
        ):
            if items:
                found.setdefault(name, []).extend(items)
    result.violations = found
    result.expectation_met = expectation_met(result, catalog)
    return result


def fallback_ratio(results: list[ScenarioResult]) -> float:
    turns = [t for r in results for t in r.turns]
    return sum(t.status in FALLBACK_STATUSES for t in turns) / len(turns) if turns else 0.0


def guide_metrics(results: list[ScenarioResult]) -> dict[str, Any]:
    """안내 지표. 위반이 아니다.

    안내 질문(책을 찾지 않는 안내 시나리오)에서 안내 tool을 부른 비율과 책 tool을 부른 수, 찾은 책
    카드가 나간 턴에서 find_book을 다시 부른 수.
    """
    asked = [
        r for r in results if r.scenario.expect == Expect.GUIDE and not r.scenario.searches_books
    ]
    with_guide = sum(GUIDE_TOOL in r.last.tools for r in asked)
    book_calls = sum(t in BOOK_TOOLS for r in asked for t in r.last.tools)
    found_turns = [t for r in results for t in r.turns if t.found]
    return {
        "guide_questions": len(asked),
        "guide_tool_rate": with_guide / len(asked) if asked else 0.0,
        "book_tool_calls_in_guide_questions": book_calls,
        "found_turns": len(found_turns),
        "find_book_after_found": sum("find_book" in t.tools for t in found_turns),
    }
