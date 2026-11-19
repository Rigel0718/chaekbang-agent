"""[platform/admin-agent-evals] 운영 에이전트 평가: 평가 기관, 라벨, 채점, 결과 파일. 가짜 LLM."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import LlmTurn, Message
from app.agent.tools import ToolSpec
from app.core.config import get_settings
from app.features.children.analytics import AUDIENCE_AXIS
from app.library.analytics.periods import PeriodPreset
from app.library.analytics.scope import BookFilter
from app.library.models.library import Library
from app.library.services import analytics
from evals.admin_agent.__main__ import METRIC_NAMES, run_all
from evals.admin_agent.fixture import build_libraries, fixed_clock
from evals.admin_agent.scenarios import SCENARIOS, Call, Scenario
from evals.admin_agent.score import ToolCallRecord, TurnRecord, numbers_in, score
from tests.agent.fakes import call, tool_turn
from tests.evals.test_librarian_eval import _spec_roots, _spec_scenarios


async def _snapshot(session: AsyncSession, library_id: int) -> list[dict]:
    axes = (AUDIENCE_AXIS,)
    results = [
        await analytics.collection_status(
            session, library_id, group_by=key, book_filter=BookFilter(), axes=axes
        )
        for key in (None, "field", "status", "audience")
    ]
    results.append(
        await analytics.loan_stats(
            session,
            library_id,
            period=PeriodPreset.LAST_90_DAYS,
            month=None,
            group_by="book",
            book_filter=BookFilter(),
            axes=axes,
            top_n=20,
        )
    )
    dumped = [r.model_dump(mode="json") for r in results]
    for d in dumped:  # id는 만들 때마다 다르다
        for item in (d.get("ranking") or {}).get("items", []):
            item.pop("library_book_id")
    return dumped


async def test_same_data(session: AsyncSession) -> None:
    """[platform/admin-agent-evals] 평가 기관 / 같은 데이터"""
    with fixed_clock():
        first = await build_libraries(session)
        second = await build_libraries(session, suffix=" 2")
        assert await _snapshot(session, first.internal_id) == await _snapshot(
            session, second.internal_id
        )


def _turn(message: str, unsupported=None, calls=(), question="질문") -> TurnRecord:
    return TurnRecord(question, message, unsupported, "completed", list(calls))


def test_partial_call_match() -> None:
    """[platform/admin-agent-evals] 시나리오 라벨 / 부분 일치"""
    scenario = Scenario("s", "q", calls=((Call("get_loan_stats", {"period": "this_month"}),),))
    calls = [
        ToolCallRecord("get_loan_stats", {"period": "this_month", "group_by": "field"}, False, {}),
        ToolCallRecord("get_loan_stats", {"period": "last_month", "group_by": None}, False, {}),
    ]
    assert score(scenario, _turn("답", calls=calls)).tool_ok
    wrong = [ToolCallRecord("get_loan_stats", {"period": "last_month"}, False, {})]
    assert not score(scenario, _turn("답", calls=wrong)).tool_ok
    fields = Scenario("s", "q", calls=((Call("x", {"fields": ["자연과학", "기술과학"]}),),))
    swapped = [ToolCallRecord("x", {"fields": ["기술과학", "자연과학"]}, False, {})]
    assert score(fields, _turn("답", calls=swapped)).tool_ok


def test_scenarios_trace_admin_eval_requirements() -> None:
    """[platform/admin-agent-evals] 시나리오 라벨 / 스펙 추적"""
    _, by_eval = _spec_scenarios(_spec_roots())
    admin = {t for t in by_eval if t.startswith("[agent/admin]")}
    assert len(admin) == 7
    covered = {trace for s in SCENARIOS for trace in s.traces}
    assert admin <= covered, admin - covered
    every, _ = _spec_scenarios(_spec_roots())
    assert covered <= every
    assert len(SCENARIOS) == 23
    assert len({s.id for s in SCENARIOS}) == 23


def test_invented_number() -> None:
    """[platform/admin-agent-evals] 평가 지표 / 지어낸 숫자"""
    scenario = Scenario("s", "q", must_say=("17",))
    result = {"loans": 17, "period": {"label": "2026년 11월 1일~19일"}}
    calls = [ToolCallRecord("get_loan_stats", {}, False, result)]
    assert score(scenario, _turn("이번 달 대출은 17건이에요.", calls=calls)).numbers_ok
    bad = score(scenario, _turn("17건이고 지난해는 42건이에요.", calls=calls))
    assert not bad.numbers_ok
    assert bad.invented == ["42"]


def test_period_label_numbers() -> None:
    """[platform/admin-agent-evals] 평가 지표 / 기간 표기의 숫자"""
    result = {"loans": 17, "period": {"label": "2026년 11월 1일~19일", "start": "2026-11-01"}}
    calls = [ToolCallRecord("get_loan_stats", {}, False, result)]
    turn = _turn("11월 1일부터 19일까지 대출은 17건이에요.", calls=calls)
    assert score(Scenario("s", "q"), turn).numbers_ok
    # 목록 번호와 KDC 주류 번호는 숫자로 보지 않거나 허용한다
    listed = _turn("1. 자연과학(KDC 400번대) 17건\n2. 문학", calls=calls)
    assert score(Scenario("s", "q"), listed).numbers_ok
    assert numbers_in("1,234권과 1.50") == ["1234", "1.5"]


def test_unsupported_match() -> None:
    """[platform/admin-agent-evals] 평가 지표 / 분류 일치"""
    scenario = Scenario("s", "누가 연체했어?", unsupported="patron_info")
    assert score(scenario, _turn("못 해요", "patron_info")).unsupported_ok
    assert not score(scenario, _turn("못 해요", "other")).unsupported_ok


def _json_files(path: Path) -> list[str]:
    return sorted(p.name for p in path.glob("*.json"))


@dataclass
class AnswerOnlyLlm:
    """첫 번째 tool이 있으면 한 번 부르고, 다음에 정해 둔 답을 낸다."""

    model: str = "fake-model"
    requests: list[dict[str, Any]] = field(default_factory=list)

    async def complete(
        self, *, system: str, tools: list[ToolSpec], messages: list[Message]
    ) -> LlmTurn:
        self.requests.append({"tools": tools})
        answered = any(getattr(m, "call_id", None) for m in messages)
        names = [t.name for t in tools]
        if not answered and "get_collection_status" in names:
            args = {"group_by": None, "fields": None, "audience": None}
            return tool_turn(call("get_collection_status", args, "c1"))
        return tool_turn(call("submit_answer", {"message": "모두 51권이에요", "unsupported": None}))


async def test_summary_files(tmp_path: Path, engine) -> None:
    """[platform/admin-agent-evals] 평가 실행과 결과 / 요약 파일"""
    scenarios = [s for s in SCENARIOS if s.id in {"total", "topic-count", "external-loans"}]
    rows = await run_all(AnswerOnlyLlm(), scenarios, tmp_path, get_settings().test_database_url)
    assert len(rows) == 3
    files = _json_files(tmp_path)
    assert files == ["01-total.json", "02-topic-count.json", "03-external-loans.json"]
    summary = (tmp_path / "summary.md").read_text(encoding="utf-8")
    for name in METRIC_NAMES.values():
        assert f"- {name}: " in summary
    total = next(r for s, _, r in rows if s.id == "total")
    assert total.passed


async def test_rolled_back(tmp_path: Path, engine) -> None:
    """[platform/admin-agent-evals] 평가 기관 / 되돌림"""
    scenarios = [s for s in SCENARIOS if s.id == "total"]
    await run_all(AnswerOnlyLlm(), scenarios, tmp_path, get_settings().test_database_url)
    async with engine.connect() as conn:
        names = await conn.scalar(
            select(func.count()).select_from(Library).where(Library.name.like("평가용 %"))
        )
        sessions = await conn.scalar(
            text("SELECT count(*) FROM chat_sessions WHERE kind = 'admin'")
        )
    assert (names, sessions) == (0, 0)


def test_must_say_alternatives() -> None:
    """[platform/admin-agent-evals] 시나리오 라벨 / 부분 일치 (있어야 할 값의 대안)"""
    scenario = Scenario("s", "q", must_say=(("어린이 실험실", "1권"),))
    result = {"groups": [{"key": "lost", "copies": 1}]}
    calls = [ToolCallRecord("get_collection_status", {}, False, result)]
    assert score(scenario, _turn("분실된 어린이 도서는 1권이에요.", calls=calls)).numbers_ok
    missing = score(scenario, _turn("분실된 책이 없어요.", calls=calls))
    assert missing.missing_say == ["어린이 실험실 | 1권"]
