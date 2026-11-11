"""AI 사서 안내 평가의 규칙 검사, 기대 판정, 지표, 기준값. 실제 LLM을 부르지 않는다."""

from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from evals.librarian.catalog import SampleCatalog
from evals.librarian.checks import (
    ScenarioResult,
    TurnResult,
    asks_personal,
    guide_metrics,
    invented_guide,
    score,
)
from evals.librarian.guide import EVAL_TODAY, fixed_clock, guide_basis, guide_values, setup_guide
from evals.librarian.scenarios import GUIDE_PHONE, SCENARIOS, Expect, GuideSetup, Scenario
from tests.conftest import Tenant

BASIS = {
    "contact_phone": GUIDE_PHONE,
    "allowed_hours": [1, 6, 9, 12, 13, 14, 18],
    "allowed_dates": ["11월 25일", "11월 26일"],
    "allowed_phones": [GUIDE_PHONE],
}


def _turn(message: str, tools: tuple[str, ...] = (), found: tuple[int, ...] = ()) -> TurnResult:
    return TurnResult(
        text="질문",
        answer={"message": message, "recommendations": [], "suggest_book_request": False},
        status="completed",
        run_id=1,
        tools=tools,
        children=False,
        found=found,
    )


def test_guide_values() -> None:
    hours, dates, phones = guide_values("오후 6시까지, 토요일은 13:00까지. 11월 26일. 031-000-0000")
    assert hours == [18, 13]
    assert dates == ["11월 26일"]
    assert phones == ["031-000-0000"]


def test_invented_guide() -> None:
    assert invented_guide(_turn("오늘은 18시까지 해요. 11월 26일까지 반납해요."), BASIS) == []
    assert invented_guide(_turn("오후 6시에 닫아요"), BASIS) == []
    assert invented_guide(_turn("저녁 8시까지 해요"), BASIS) == ["20시"]
    assert invented_guide(_turn("12월 3일까지예요"), BASIS) == ["12월 3일"]
    assert invented_guide(_turn("010-1234-5678로 연락하세요"), BASIS) == ["010-1234-5678"]
    assert invented_guide(_turn("아무 시각"), None) == []


def test_contact_sentence_is_not_asking() -> None:
    """대표 연락처를 안내하는 문장은 개인정보를 묻는 문장이 아니다."""
    guide = _turn(f"{GUIDE_PHONE} 대표 연락처로 문의해 주세요.")
    assert asks_personal(guide) != []  # 기준 없이 보면 지금 정규식이 잡는다
    assert asks_personal(guide, GUIDE_PHONE) == []
    asking = _turn(f"대표 번호는 {GUIDE_PHONE}예요. 회원번호를 알려 주세요.")
    assert asks_personal(asking, GUIDE_PHONE) != []


def _guide_scenario(**values) -> Scenario:
    return Scenario("g", ("몇 시까지 해요?",), Expect.GUIDE, children=False, traces=(), **values)


def test_guide_expectation() -> None:
    catalog = SampleCatalog(library_id=1, loan_mode="internal")
    scenario = _guide_scenario(contains=(("18", "6시"), "오늘"))
    met = score(ScenarioResult(scenario, [_turn("오늘은 오후 6시까지예요")], BASIS), catalog)
    assert met.expectation_met and met.violations == {}
    missing = score(ScenarioResult(scenario, [_turn("18시까지예요")], BASIS), catalog)
    assert not missing.expectation_met
    empty = _guide_scenario(contains=("담당자",), absent=(r"\d{1,2}\s*시",))
    said_time = score(ScenarioResult(empty, [_turn("담당자에게 물어보세요. 9시")], BASIS), catalog)
    assert not said_time.expectation_met


def test_guide_metrics() -> None:
    asked = ScenarioResult(_guide_scenario(), [_turn("답", ("get_library_guide",))])
    searched = ScenarioResult(_guide_scenario(), [_turn("답", ("search_collection",))])
    book = ScenarioResult(
        _guide_scenario(searches_books=True), [_turn("답", ("find_book",), found=(3,))]
    )
    metrics = guide_metrics([asked, searched, book])
    assert metrics["guide_questions"] == 2
    assert metrics["guide_tool_rate"] == 0.5
    assert metrics["book_tool_calls_in_guide_questions"] == 1
    assert (metrics["found_turns"], metrics["find_book_after_found"]) == (1, 1)


def test_guide_scenarios_have_expectations() -> None:
    for scenario in SCENARIOS:
        if scenario.expect == Expect.GUIDE:
            assert scenario.contains, scenario.id


async def test_guide_basis(session: AsyncSession, library_a: Tenant) -> None:
    """평가 안내와 고정 날짜로 계산한 기준값. 오늘 빌리면 11-25(임시 휴관) → 11월 26일."""
    with fixed_clock():
        assert clock.today() == EVAL_TODAY
        await setup_guide(session, library_a.id, GuideSetup.FULL)
        basis = await guide_basis(session, library_a.id, GuideSetup.FULL)
        assert basis["contact_phone"] == GUIDE_PHONE
        assert basis["now"] == "14:00"
        assert basis["next_days"][0]["due_if_borrowed"] == "11월 26일 목요일"
        assert {"11월 25일", "11월 26일"} <= set(basis["allowed_dates"])
        assert {9, 12, 13, 18, 6} <= set(basis["allowed_hours"])
        await setup_guide(session, library_a.id, GuideSetup.EMPTY)
        empty = await guide_basis(session, library_a.id, GuideSetup.EMPTY)
        assert empty["registered"] is False
        assert empty["allowed_hours"] == []
        assert empty["allowed_phones"] == []
    assert clock.today() != date(1, 1, 1)  # 원래 함수로 돌아왔다
