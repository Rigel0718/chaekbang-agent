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
from evals.admin_agent.fixture import (
    CURATION_BOOKS,
    PENDING_CURATION,
    build_libraries,
    fixed_clock,
)
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


async def test_curation_topics(session: AsyncSession) -> None:
    """[platform/admin-agent-evals] 평가 기관 / 큐레이션 주제"""
    from app.library.recommendation.search import search_collection

    with fixed_clock():
        libraries = await build_libraries(session)
    for library_id in (libraries.curation_internal_id, libraries.curation_external_id):
        for topic in ("공룡", "우주"):
            found = await search_collection(session, library_id, [topic])
            assert len(found) >= 3, (library_id, topic)
            assert all(c.recommendable for c in found)
    # 분석 기관의 숫자는 그대로다(큐레이션 책은 다른 기관에만 있다)
    assert not set(libraries.titles) & {b[0] for b in CURATION_BOOKS if b[0] != "공룡 대탐험"}


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
    assert len(admin) == 10
    covered = {trace for s in SCENARIOS for trace in s.traces}
    assert admin <= covered, admin - covered
    every, _ = _spec_scenarios(_spec_roots())
    assert covered <= every
    assert len(SCENARIOS) == 27
    assert len({s.id for s in SCENARIOS}) == 27


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
        curations = await conn.scalar(
            text("SELECT count(*) FROM curations WHERE title = :t"), {"t": PENDING_CURATION}
        )
    assert (names, sessions, curations) == (0, 0, 0)


def test_must_say_alternatives() -> None:
    """[platform/admin-agent-evals] 시나리오 라벨 / 부분 일치 (있어야 할 값의 대안)"""
    scenario = Scenario("s", "q", must_say=(("어린이 실험실", "1권"),))
    result = {"groups": [{"key": "lost", "copies": 1}]}
    calls = [ToolCallRecord("get_collection_status", {}, False, result)]
    assert score(scenario, _turn("분실된 어린이 도서는 1권이에요.", calls=calls)).numbers_ok
    missing = score(scenario, _turn("분실된 책이 없어요.", calls=calls))
    assert missing.missing_say == ["어린이 실험실 | 1권"]


def _searched(*ids: int) -> ToolCallRecord:
    return ToolCallRecord(
        "search_collection", {}, False, {"books": [{"library_book_id": i} for i in ids]}
    )


def _drafted(*ids: int, status: str = "pending_approval") -> ToolCallRecord:
    return ToolCallRecord(
        "draft_curation", {"library_book_ids": list(ids)}, False, {"status": status}
    )


def test_draft_from_unsearched_book() -> None:
    """[platform/admin-agent-evals] 평가 지표 / 검색하지 않은 책"""
    scenario = Scenario("s", "공룡 큐레이션", draft=True)
    ok = [_searched(1, 2, 3, 4), _drafted(1, 2, 3)]
    assert score(scenario, _turn("승인 대기로 올렸어요", calls=ok)).draft_ok
    outside = [_searched(1, 2, 3), _drafted(1, 2, 9)]
    result = score(scenario, _turn("승인 대기로 올렸어요", calls=outside))
    assert not result.draft_ok
    assert not result.passed


def test_unexpected_draft() -> None:
    """[platform/admin-agent-evals] 평가 지표 / 기대하지 않은 초안"""
    scenario = Scenario("s", "몇 권이야?")
    assert score(scenario, _turn("51권", calls=[])).draft_ok
    assert not score(
        scenario, _turn("51권", calls=[_searched(1, 2, 3), _drafted(1, 2, 3)])
    ).draft_ok


def test_draft_count_status_and_notice() -> None:
    """[platform/admin-agent-evals] 평가 지표: 초안은 하나, 승인 대기, 3~10권, 안내 낱말"""
    scenario = Scenario("s", "q", draft=True)
    searched = _searched(*range(1, 13))
    assert not score(scenario, _turn("승인 대기", calls=[searched])).draft_ok
    assert not score(scenario, _turn("승인 대기", calls=[searched, _drafted(1, 2)])).draft_ok
    assert not score(
        scenario, _turn("승인 대기", calls=[searched, _drafted(1, 2, 3, status="draft")])
    ).draft_ok
    assert not score(scenario, _turn("만들었어요", calls=[searched, _drafted(1, 2, 3)])).draft_ok
    twice = [searched, _drafted(1, 2, 3), _drafted(4, 5, 6)]
    assert not score(scenario, _turn("승인 대기", calls=twice)).draft_ok


@dataclass
class CurationLlm:
    """공룡을 찾고, 결과의 앞 3권으로 초안을 만든 뒤 승인 대기 안내로 답한다."""

    model: str = "fake-model"
    requests: list[dict[str, Any]] = field(default_factory=list)

    async def complete(
        self, *, system: str, tools: list[ToolSpec], messages: list[Message]
    ) -> LlmTurn:
        import json

        from app.agent.llm import ToolResult

        self.requests.append({"tools": tools})
        results = [m for m in messages if isinstance(m, ToolResult)]
        if not results:
            return tool_turn(call("search_collection", {"keywords": ["공룡"]}, "s1"))
        if len(results) == 1:
            ids = [b["library_book_id"] for b in json.loads(results[0].content)["books"]][:3]
            args = {
                "title": "공룡 특집",
                "intro": None,
                "library_book_ids": ids,
                "reasons": ["공룡 책"] * len(ids),
            }
            return tool_turn(call("draft_curation", args, "d1"))
        message = "공룡 특집 3권을 승인 대기로 올렸어요. 관리 화면에서 승인하면 게시돼요."
        return tool_turn(call("submit_answer", {"message": message, "unsupported": None}))


async def test_curation_scenario_end_to_end(tmp_path: Path, engine) -> None:
    """[platform/admin-agent-evals] 평가 지표: 초안 충실도를 실제 경로의 tool 결과로 잰다"""
    scenarios = [s for s in SCENARIOS if s.id in {"curation-dinosaur", "curation-external"}]
    rows = await run_all(CurationLlm(), scenarios, tmp_path, get_settings().test_database_url)
    for scenario, turn, result in rows:
        assert result.passed, (scenario.id, result, turn)
        assert [c.name for c in turn.calls] == ["search_collection", "draft_curation"]
        assert turn.calls[0].result["books"]


def test_science_word_accepts_both_readings() -> None:
    """[platform/admin-agent-evals] 시나리오 라벨 / 부분 일치 (과학책의 두 읽기, 2026-11-21 넓힘)"""
    [scenario] = [s for s in SCENARIOS if s.id == "science-word"]
    for fields, copies in ((["자연과학"], 8), (["자연과학", "기술과학"], 14)):
        calls = [
            ToolCallRecord("get_collection_status", {"fields": fields}, False, {"copies": copies})
        ]
        result = score(scenario, _turn(f"과학책은 {copies}권이에요(KDC 기준).", calls=calls))
        assert result.passed, (fields, result)
