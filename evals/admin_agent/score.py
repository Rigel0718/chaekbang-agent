"""운영 에이전트 평가의 채점. LLM 채점은 없고 코드로만 판정한다.

- tool 선택: 시나리오의 기대 호출이 실제 호출(실행 기록의 입력)에 모두 있다. 적은 값만 맞춰 본다.
- 숫자 충실도: `must_say`가 모두 답에 있고(튜플 항목은 그중 하나), 답의 모든 숫자가 그 턴의 tool
  결과, 질문, 허용 숫자 안에 있다. 허용 숫자는 KDC 주류 번호(000~900, "400번대")다. 목록 번호
  (줄 앞의 `1.`, `2)`)는 숫자로 보지 않는다. `absent`의 값이 답에 있으면 틀린다.
- 못 하는 분석 분류: 답의 `unsupported`가 라벨과 같다.
- 초안 충실도: 초안을 기대하면 성공한 `draft_curation`이 하나이고 결과가 승인 대기이며, 그 책
  (`library_book_ids`)이 모두 같은 턴의 `search_collection` 결과에 있고, 서로 다른 3~10권이고, 답에
  `draft_say`가 있다. 기대하지 않으면 성공한 `draft_curation`이 없어야 맞다.
  연체 안내문 틀을 기대하면(`notice`) 성공한 `draft_overdue_notice`가 하나이고 결과가 승인 대기이며,
  그 틀 문장(러너가 저장된 행에서 읽은 `templates`)과 답에 평가 기관 회원 값(`MEMBER_MARKS`)이
  없고, 답에 `draft_say`가 있다. 기대하지 않으면 성공한 `draft_overdue_notice`가 없어야 맞다.
"""

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import Any

from evals.admin_agent.scenarios import MEMBER_MARKS, Call, Scenario

_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_LIST_MARK = re.compile(r"(?m)^\s*(?:[-*]\s*)?\d+[.)]\s")
KDC_NUMBERS = {f"{i}00" for i in range(10)} | {"000"}


@dataclass(frozen=True)
class ToolCallRecord:
    name: str
    args: dict[str, Any]
    is_error: bool
    result: Any = None  # 같은 데이터로 다시 부른 결과(오류면 None)


@dataclass
class TurnRecord:
    question: str
    message: str
    unsupported: str | None
    status: str
    calls: list[ToolCallRecord]
    templates: list[str] = field(default_factory=list)  # 이 턴에 만든 안내문 틀 문장
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class Score:
    tool_ok: bool
    numbers_ok: bool
    unsupported_ok: bool
    draft_ok: bool = True
    draft_notes: list[str] = field(default_factory=list)
    missing_calls: list[str] = field(default_factory=list)
    missing_say: list[str] = field(default_factory=list)
    invented: list[str] = field(default_factory=list)
    present_absent: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.tool_ok and self.numbers_ok and self.unsupported_ok and self.draft_ok


def _normalize(number: str) -> str:
    if "." in number:
        number = number.rstrip("0").rstrip(".")
    return number.lstrip("0") or "0"


def numbers_in(text: str) -> list[str]:
    cleaned = _LIST_MARK.sub(" ", text.replace(",", ""))
    return [_normalize(n) for n in _NUMBER.findall(cleaned)]


def _walk(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for v in value.values():
            yield from _walk(v)
    elif isinstance(value, list):
        for v in value:
            yield from _walk(v)
    elif isinstance(value, bool) or value is None:
        return
    elif isinstance(value, int | float):
        yield _normalize(repr(value))
    elif isinstance(value, str):
        yield from numbers_in(value)


def allowed_numbers(question: str, results: Sequence[Any]) -> set[str]:
    allowed = set(numbers_in(question)) | {_normalize(n) for n in KDC_NUMBERS}
    for result in results:
        allowed |= set(_walk(result))
    return allowed


def _matches(expected: Call, actual: ToolCallRecord) -> bool:
    if actual.name != expected.tool or actual.is_error:
        return False
    for key, value in expected.args.items():
        got = actual.args.get(key)
        if isinstance(value, list):
            if set(got or ()) != set(value):
                return False
        elif got != value:
            return False
    return True


def _label(options: Sequence[Call]) -> str:
    return " | ".join(f"{c.tool}{json.dumps(c.args, ensure_ascii=False)}" for c in options)


DRAFT_MIN, DRAFT_MAX = 3, 10


def notice_notes(scenario: Scenario, turn: TurnRecord) -> list[str]:
    """연체 안내문 틀의 틀린 까닭. 비면 맞다."""
    notices = [c for c in turn.calls if c.name == "draft_overdue_notice" and not c.is_error]
    if not scenario.notice:
        return [f"기대하지 않은 안내문 틀 {len(notices)}개"] if notices else []
    if len(notices) != 1:
        return [f"안내문 틀 {len(notices)}개"]
    notes = []
    if (notices[0].result or {}).get("status") != "pending_approval":
        notes.append("승인 대기가 아님")
    leaked = sorted({m for m in MEMBER_MARKS for body in turn.templates if m in body})
    if leaked:
        notes.append(f"틀에 회원 값 {leaked}")
    if any(m in turn.message for m in MEMBER_MARKS):
        notes.append("답에 회원 값")
    if scenario.draft_say and not any(w in turn.message for w in scenario.draft_say):
        notes.append(f"안내 낱말 없음 {list(scenario.draft_say)}")
    return notes


def draft_notes(scenario: Scenario, turn: TurnRecord) -> list[str]:
    """초안 충실도의 틀린 까닭(큐레이션과 연체 안내문 틀). 비면 맞다."""
    return curation_notes(scenario, turn) + notice_notes(scenario, turn)


def curation_notes(scenario: Scenario, turn: TurnRecord) -> list[str]:
    drafts = [c for c in turn.calls if c.name == "draft_curation" and not c.is_error]
    if not scenario.draft:
        return [f"기대하지 않은 초안 {len(drafts)}개"] if drafts else []
    if len(drafts) != 1:
        return [f"초안 {len(drafts)}개"]
    [draft] = drafts
    notes = []
    if (draft.result or {}).get("status") != "pending_approval":
        notes.append("승인 대기가 아님")
    ids = list(draft.args.get("library_book_ids") or [])
    searched = {
        book["library_book_id"]
        for c in turn.calls
        if c.name == "search_collection" and isinstance(c.result, dict)
        for book in c.result.get("books", [])
    }
    outside = [i for i in ids if i not in searched]
    if outside:
        notes.append(f"검색 결과에 없는 책 {outside}")
    if not DRAFT_MIN <= len(set(ids)) <= DRAFT_MAX:
        notes.append(f"권수 {len(set(ids))}")
    if scenario.draft_say and not any(w in turn.message for w in scenario.draft_say):
        notes.append(f"안내 낱말 없음 {list(scenario.draft_say)}")
    return notes


def score(scenario: Scenario, turn: TurnRecord) -> Score:
    missing_calls = [
        _label(options)
        for options in scenario.calls
        if not any(_matches(c, actual) for c in options for actual in turn.calls)
    ]
    message = turn.message
    allowed = allowed_numbers(turn.question, [c.result for c in turn.calls if c.result is not None])
    invented = sorted({n for n in numbers_in(message) if n not in allowed})
    plain = message.replace(",", "")
    missing_say = [
        value if isinstance(value, str) else " | ".join(value)
        for value in scenario.must_say
        if not any(v in plain for v in ((value,) if isinstance(value, str) else value))
    ]
    present_absent = [value for value in scenario.absent if value in message]
    return Score(
        tool_ok=not missing_calls,
        numbers_ok=not invented and not missing_say and not present_absent,
        unsupported_ok=turn.unsupported == scenario.unsupported,
        draft_ok=not (notes := draft_notes(scenario, turn)),
        draft_notes=notes,
        missing_calls=missing_calls,
        missing_say=missing_say,
        invented=invented,
        present_absent=present_absent,
    )
