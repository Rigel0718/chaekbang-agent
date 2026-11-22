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
from app.library.services.purchase_candidates import purchase_candidates
from evals.admin_agent.__main__ import METRIC_NAMES, run_all
from evals.admin_agent.fixture import (
    CURATION_BOOKS,
    PENDING_CURATION,
    PENDING_PURCHASE,
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


async def _candidates(session: AsyncSession, library_id: int) -> dict:
    return (await purchase_candidates(session, library_id)).model_dump(mode="json")


async def test_same_data(session: AsyncSession) -> None:
    """[platform/admin-agent-evals] 평가 기관 / 같은 데이터"""
    with fixed_clock():
        first = await build_libraries(session)
        second = await build_libraries(session, suffix=" 2")
        assert await _snapshot(session, first.internal_id) == await _snapshot(
            session, second.internal_id
        )
        for a, b in (
            (first.internal_id, second.internal_id),
            (first.curation_external_id, second.curation_external_id),
        ):
            assert await _candidates(session, a) == await _candidates(session, b)


async def test_wishes_do_not_change_analysis_labels(session: AsyncSession) -> None:
    """[platform/admin-agent-evals] 평가 기관 / 희망도서가 분석 숫자를 바꾸지 않음

    희망도서·ISBN·승인 대기 요청서를 넣은 평가 기관에서 `scenarios.py` 머리말의 분석 값(라벨의
    근거)이 그대로다.
    """
    with fixed_clock():
        libraries = await build_libraries(session)
        lib = libraries.internal_id
        axes = (AUDIENCE_AXIS,)
        plain = BookFilter()

        async def status(group_by):
            return await analytics.collection_status(
                session, lib, group_by=group_by, book_filter=plain, axes=axes
            )

        async def loans(period, group_by=None):
            return await analytics.loan_stats(
                session, lib, period=period, month=None, group_by=group_by,
                book_filter=plain, axes=axes, top_n=10,
            )  # fmt: skip

        total = await status(None)
        assert (total.copies, total.titles, total.withdrawn_copies) == (51, 47, 2)
        assert {g.label: g.copies for g in (await status("field")).groups}["문학"] == 16
        assert {g.key: g.copies for g in (await status("audience")).groups}["children"] == 13
        assert {g.key: g.copies for g in (await status("acquisition_type")).groups}["donated"] == 6
        this_month = await loans(PeriodPreset.THIS_MONTH, "field")
        assert this_month.loans == 17
        assert {g.label: g.loans for g in this_month.groups}["문학"] == 11
        assert (this_month.current.on_loan, this_month.current.overdue) == (6, 2)
        assert (await loans(PeriodPreset.LAST_MONTH)).loans == 15
        unborrowed = await analytics.unborrowed_books(
            session, lib, period=PeriodPreset.LAST_365_DAYS, month=None,
            book_filter=plain, axes=axes, limit=20,
        )  # fmt: skip
        assert unborrowed.total == 22
        found = await purchase_candidates(session, lib)
        assert [(w.title, w.request_count) for w in found.wishes] == [
            ("숲속 동물 사전", 2),
            ("별자리 이야기", 1),
            ("우리 동네 지도", 1),
        ]
        assert found.wishes_without_isbn == 1 and found.popular


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
    assert len(admin) == 19
    covered = {trace for s in SCENARIOS for trace in s.traces}
    assert admin <= covered, admin - covered
    every, _ = _spec_scenarios(_spec_roots())
    assert covered <= every
    assert len(SCENARIOS) == 36
    assert len({s.id for s in SCENARIOS}) == 36


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


NOTICE_BODY = "{이름}님, '{서명}' 반납 예정일({반납예정일})이 {연체일수}일 지났어요."


@dataclass
class NoticeLlm:
    """안내문 틀 초안 tool이 있으면 틀을 올리고 승인 대기 안내로 답한다. 없으면 바로 답한다."""

    model: str = "fake-model"
    body: str = NOTICE_BODY

    async def complete(
        self, *, system: str, tools: list[ToolSpec], messages: list[Message]
    ) -> LlmTurn:
        answered = any(getattr(m, "call_id", None) for m in messages)
        if not answered and "draft_overdue_notice" in [t.name for t in tools]:
            return tool_turn(call("draft_overdue_notice", {"template": self.body}, "n1"))
        message = "승인 대기로 올렸어요. 관리 화면에서 승인하면 연체 안내 목록이 만들어져요."
        return tool_turn(call("submit_answer", {"message": message, "unsupported": None}))


async def test_rolled_back(tmp_path: Path, engine) -> None:
    """[platform/admin-agent-evals] 평가 기관 / 되돌림"""
    scenarios = [s for s in SCENARIOS if s.id in {"total", "overdue-notice"}]
    await run_all(NoticeLlm(), scenarios, tmp_path, get_settings().test_database_url)
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
        templates = await conn.scalar(
            text("SELECT count(*) FROM overdue_notice_templates WHERE body = :b"),
            {"b": NOTICE_BODY},
        )
        purchases = await conn.scalar(
            text("SELECT count(*) FROM purchase_requests WHERE title = :t"),
            {"t": PENDING_PURCHASE},
        )
        wishes = await conn.scalar(
            text("SELECT count(*) FROM book_requests WHERE title = '숲속 동물 사전'")
        )
    assert (names, sessions, curations, templates, purchases, wishes) == (0, 0, 0, 0, 0, 0)


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


def _noticed(status: str = "pending_approval") -> ToolCallRecord:
    return ToolCallRecord("draft_overdue_notice", {}, False, {"status": status, "template_id": 1})


def test_template_with_member_name() -> None:
    """[platform/admin-agent-evals] 평가 지표 / 회원 이름이 든 틀"""
    scenario = Scenario("s", "q", notice=True)
    ok = _turn("승인 대기로 올렸어요", calls=[_noticed()])
    ok.templates = ["{이름}님 {서명} {반납예정일}"]
    assert score(scenario, ok).draft_ok
    leaked = _turn("승인 대기로 올렸어요", calls=[_noticed()])
    leaked.templates = ["평가회원1님 {서명} {반납예정일}"]
    result = score(scenario, leaked)
    assert not result.draft_ok
    assert any("회원 값" in n for n in result.draft_notes)
    in_answer = _turn("평가회원1님 안내문을 승인 대기로 올렸어요", calls=[_noticed()])
    in_answer.templates = ["{이름}님 {서명} {반납예정일}"]
    assert not score(scenario, in_answer).draft_ok


def test_unexpected_template_and_notice_rules() -> None:
    """[platform/admin-agent-evals] 평가 지표 / 기대하지 않은 초안 (안내문 틀)"""
    analysis = Scenario("s", "몇 권이야?")
    assert not score(analysis, _turn("51권", calls=[_noticed()])).draft_ok
    notice = Scenario("s", "q", notice=True)
    assert not score(notice, _turn("승인 대기", calls=[])).draft_ok
    assert not score(notice, _turn("승인 대기", calls=[_noticed("draft")])).draft_ok
    assert not score(notice, _turn("만들었어요", calls=[_noticed()])).draft_ok
    assert not score(notice, _turn("승인 대기", calls=[_noticed(), _noticed()])).draft_ok


async def test_notice_scenarios_end_to_end(tmp_path: Path, engine) -> None:
    """[platform/admin-agent-evals] 평가 지표: 안내문 틀을 실제 경로의 저장된 행으로 잰다"""
    ids = {"overdue-notice", "overdue-notice-name", "overdue-notice-external"}
    scenarios = [s for s in SCENARIOS if s.id in ids]
    rows = await run_all(NoticeLlm(), scenarios, tmp_path, get_settings().test_database_url)
    by_id = {s.id: (turn, result) for s, turn, result in rows}
    for scenario_id in ("overdue-notice", "overdue-notice-name"):
        turn, result = by_id[scenario_id]
        assert result.draft_ok, (scenario_id, result)
        assert turn.templates == [NOTICE_BODY]
    external_turn, _ = by_id["overdue-notice-external"]
    assert external_turn.calls == []
    leaky = NoticeLlm(body="평가회원1님 {서명} {반납예정일}")
    [(_, _, leaked)] = await run_all(
        leaky, [s for s in SCENARIOS if s.id == "overdue-notice-name"], tmp_path / "leak",
        get_settings().test_database_url,
    )  # fmt: skip
    assert not leaked.draft_ok


# --- 구매 요청서 ---


def _offered(*isbns: str) -> ToolCallRecord:
    return ToolCallRecord(
        "list_purchase_candidates",
        {"period": None},
        False,
        {"wishes": [{"isbn": i, "request_count": 1} for i in isbns], "popular": []},
    )


def _purchased(*isbns: str, status: str = "pending_approval") -> ToolCallRecord:
    items = [{"isbn": i, "quantity": 1, "reason": None} for i in isbns]
    return ToolCallRecord(
        "draft_purchase_request", {"items": items}, False, {"status": status, "item_count": 1}
    )


ISBN_A, ISBN_B = "9791190000017", "9791190000024"


def test_purchase_item_outside_candidates() -> None:
    """[platform/admin-agent-evals] 평가 지표 / 후보에 없는 요청서 항목"""
    scenario = Scenario("s", "q", purchase=True)
    ok = [_offered(ISBN_A), _purchased("979-11-900-0001-7")]
    assert score(scenario, _turn("승인 대기로 올렸어요", calls=ok)).draft_ok
    outside = score(
        scenario, _turn("승인 대기로 올렸어요", calls=[_offered(ISBN_A), _purchased(ISBN_B)])
    )
    assert not outside.draft_ok and not outside.passed
    assert any("후보에 없는 ISBN" in n for n in outside.draft_notes)
    assert not score(scenario, _turn("승인 대기", calls=[_offered(ISBN_A)])).draft_ok
    pending_not = [_offered(ISBN_A), _purchased(ISBN_A, status="draft")]
    assert not score(scenario, _turn("승인 대기", calls=pending_not)).draft_ok
    named = _turn("평가회원1님 신청 책을 승인 대기로 올렸어요", calls=ok)
    assert not score(scenario, named).draft_ok


def test_unexpected_purchase_request() -> None:
    """[platform/admin-agent-evals] 평가 지표 / 기대하지 않은 초안 (구매 요청서)"""
    analysis = Scenario("s", "몇 권이야?")
    calls = [_offered(ISBN_A), _purchased(ISBN_A)]
    assert not score(analysis, _turn("51권", calls=calls)).draft_ok


def test_budget_numbers() -> None:
    """[platform/admin-agent-evals] 평가 지표 / 예산 숫자"""
    [scenario] = [s for s in SCENARIOS if s.id == "purchase-budget"]
    ok = _turn(
        "금액은 관리 화면의 요청서 상세에서 정가로 계산돼요.", "other", question=scenario.question
    )
    assert score(scenario, ok).passed
    bad = _turn(
        "예산은 42,000원쯤이에요. 관리 화면에서 확인하세요.", "other", question=scenario.question
    )
    result = score(scenario, bad)
    assert not result.numbers_ok and result.invented == ["42000"]


@dataclass
class PurchaseLlm:
    """구매 후보를 보고 첫 희망도서·첫 인기 ISBN으로 초안을 올린 뒤 승인 대기 안내로 답한다."""

    model: str = "fake-model"

    async def complete(
        self, *, system: str, tools: list[ToolSpec], messages: list[Message]
    ) -> LlmTurn:
        import json

        from app.agent.llm import ToolResult

        results = [m for m in messages if isinstance(m, ToolResult)]
        if not results:
            return tool_turn(call("list_purchase_candidates", {"period": None}, "p1"))
        if len(results) == 1:
            found = json.loads(results[0].content)
            isbns = [r["isbn"] for r in (found["wishes"][:1] + found["popular"][:1])]
            args = {
                "title": "보충 구매",
                "note": None,
                "period": None,
                "items": [{"isbn": i, "quantity": 1, "reason": None} for i in isbns],
            }
            return tool_turn(call("draft_purchase_request", args, "p2"))
        message = "요청서를 승인 대기로 올렸어요. 관리 화면에서 금액을 확인하고 승인하면 확정돼요."
        return tool_turn(call("submit_answer", {"message": message, "unsupported": None}))


async def test_purchase_scenarios_end_to_end(tmp_path: Path, engine) -> None:
    """[platform/admin-agent-evals] 평가 지표: 요청서 초안 충실도를 실제 경로의 tool 결과로 잰다"""
    scenarios = [s for s in SCENARIOS if s.id in {"purchase-draft", "purchase-external"}]
    rows = await run_all(PurchaseLlm(), scenarios, tmp_path, get_settings().test_database_url)
    for scenario, turn, result in rows:
        assert result.passed, (scenario.id, result, turn)
        assert [c.name for c in turn.calls] == [
            "list_purchase_candidates",
            "draft_purchase_request",
        ]
        found = turn.calls[0].result
        assert found["wishes"] and found["popular"], scenario.id
        assert len(turn.calls[1].args["items"]) == 2
    external = next(t for s, t, _ in rows if s.id == "purchase-external").calls[0].result
    assert external["basis"] == "imported_status" and "loans" not in external["popular"][0]
