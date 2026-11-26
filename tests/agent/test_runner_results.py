"""[agent/runner] 결과 사건과 tool의 화면용 변환. 가짜 LLM과 가짜 tool만 쓴다."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import records
from app.agent.models import AgentRun, RunStatus
from app.agent.runner import AnswerEvent, DoneEvent, ResultEvent, StatusEvent, run
from app.agent.tools import Tool
from tests.agent.fakes import (
    FALLBACK,
    LLM_DOWN,
    NOT_FOUND,
    EchoInput,
    FakeLlm,
    Recorder,
    RejectIds,
    answer_turn,
    answers,
    call,
    collect,
    done,
    drop_items,
    echo_tool,
    profile,
    tool_turn,
)
from tests.conftest import Tenant

SECRET = "화면 전용 비밀값"


def shown_tool(name: str = "echo", handler: Any = None, present: Any = None) -> Tool:
    """입력 낱말과 결과를 묶은 화면용 값을 내는 tool."""
    return Tool(
        name,
        "찾기",
        EchoInput,
        handler or Recorder(result={"found": name}),
        f"{name} 찾는 중",
        present=present or (lambda data, output: {"shown": data.keyword, "from": output}),
    )


def results(events: list[Any]) -> list[Any]:
    return [e.value for e in events if isinstance(e, ResultEvent)]


async def test_result_event_order(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 진행 사건 / 결과 사건의 순서"""
    llm = FakeLlm(
        [
            tool_turn(call("first", {"keyword": "a"}, "c1")),
            tool_turn(call("second", {"keyword": "b"}, "c2")),
            answer_turn(),
        ]
    )
    prof = profile(shown_tool("first"), shown_tool("second"))
    events = await collect(session, llm, prof, library_a.id)
    assert [type(e) for e in events] == [
        StatusEvent,
        StatusEvent,
        ResultEvent,
        ResultEvent,
        AnswerEvent,
        DoneEvent,
    ]
    assert results(events) == [
        {"shown": "a", "from": {"found": "first"}},
        {"shown": "b", "from": {"found": "second"}},
    ]


async def test_result_events_with_repaired_answer(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 진행 사건 / 정리한 답의 결과 사건"""
    prof = profile(
        shown_tool(), final_checks=(RejectIds({9}),), repair=drop_items, max_check_retries=1
    )
    llm = FakeLlm(
        [
            tool_turn(call("echo", {"keyword": "a"})),
            answer_turn(items=[9, 1]),
            answer_turn(items=[9, 2]),
        ]
    )
    events = await collect(session, llm, prof, library_a.id)
    assert done(events).status == RunStatus.REPAIRED
    assert [type(e) for e in events][-3:] == [ResultEvent, AnswerEvent, DoneEvent]
    assert len(results(events)) == 1


async def test_no_result_events_on_call_limit(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 진행 사건 / 고정 답이면 결과 사건 없음 (호출 한도)"""
    script = [tool_turn(call("echo", {"keyword": "a"})) for _ in range(3)]
    events = await collect(
        session, FakeLlm(script), profile(shown_tool(), max_llm_calls=2), library_a.id
    )
    assert answers(events) == [FALLBACK]
    assert results(events) == []


async def test_no_result_events_on_llm_failure(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 진행 사건 / 고정 답이면 결과 사건 없음 (LLM 호출 실패)"""
    llm = FakeLlm([tool_turn(call("echo", {"keyword": "a"})), LLM_DOWN])
    events = await collect(session, llm, profile(shown_tool()), library_a.id)
    assert done(events).status == RunStatus.FAILED
    assert results(events) == []


async def test_no_result_events_on_unexpected_error(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/runner] 진행 사건 / 고정 답이면 결과 사건 없음 (예상하지 못한 예외)"""
    broken = Recorder(error=RuntimeError("내부"))
    llm = FakeLlm(
        [
            tool_turn(call("first", {"keyword": "a"}, "c1")),
            tool_turn(call("second", {"keyword": "b"}, "c2")),
        ]
    )
    prof = profile(shown_tool("first"), shown_tool("second", handler=broken))
    events = await collect(session, llm, prof, library_a.id)
    assert done(events).status == RunStatus.FAILED
    assert results(events) == []


async def test_no_result_events_when_consumer_stops(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/runner] 진행 사건 / 중단이면 결과 사건 없음"""
    llm = FakeLlm(
        [
            tool_turn(call("first", {"keyword": "a"}, "c1")),
            tool_turn(call("second", {"keyword": "b"}, "c2")),
            answer_turn(),
        ]
    )
    stream = run(
        session=session,
        llm=llm,
        profile=profile(shown_tool("first"), shown_tool("second")),
        library_id=library_a.id,
        user_text="책",
    )
    seen = [await anext(stream), await anext(stream)]  # 두 tool의 진행 문구
    await stream.aclose()
    assert [type(e) for e in seen] == [StatusEvent, StatusEvent]
    row = await session.scalar(select(AgentRun).where(AgentRun.library_id == library_a.id))
    assert row is not None and row.status == RunStatus.CANCELLED


async def test_present_value_is_carried(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] tool의 화면용 변환 / 값을 돌려준 변환"""
    value = object()
    tool = shown_tool(present=lambda data, output: value)
    llm = FakeLlm([tool_turn(call("echo", {"keyword": "a"})), answer_turn()])
    events = await collect(session, llm, profile(tool), library_a.id)
    assert results(events) == [value]
    assert results(events)[0] is value


async def test_present_none(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] tool의 화면용 변환 / 없음을 돌려준 변환"""
    tool = shown_tool(present=lambda data, output: None)
    llm = FakeLlm([tool_turn(call("echo", {"keyword": "a"})), answer_turn()])
    events = await collect(session, llm, profile(tool), library_a.id)
    assert [type(e) for e in events] == [StatusEvent, AnswerEvent, DoneEvent]


async def test_tool_without_present(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] tool의 화면용 변환 / 변환을 고르지 않은 tool"""
    llm = FakeLlm([tool_turn(call("echo", {"keyword": "a"})), answer_turn()])
    events = await collect(session, llm, profile(echo_tool()), library_a.id)
    assert [type(e) for e in events] == [StatusEvent, AnswerEvent, DoneEvent]


async def test_failed_calls_have_no_result(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] tool의 화면용 변환 / 오류로 끝난 호출"""
    llm = FakeLlm(
        [
            tool_turn(call("missing", {"keyword": "a"}, "c1")),  # 도메인 오류
            tool_turn(call("echo", {"wrong": "a"}, "c2")),  # 입력 검증 오류
            tool_turn(call("echo", {"keyword": "ok"}, "c3")),
            answer_turn(),
        ]
    )
    prof = profile(shown_tool("missing", handler=Recorder(error=NOT_FOUND)), shown_tool())
    events = await collect(session, llm, prof, library_a.id)
    assert done(events).status == RunStatus.COMPLETED
    assert results(events) == [{"shown": "ok", "from": {"found": "echo"}}]


async def test_present_receives_input_and_output(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] tool의 화면용 변환 / 변환 입력"""
    seen: list[tuple[Any, Any]] = []

    def present(data: Any, output: Any) -> None:
        seen.append((data, output))

    tool = shown_tool(handler=Recorder(result={"n": 3}), present=present)
    llm = FakeLlm([tool_turn(call("echo", {"keyword": "공룡"})), answer_turn()])
    await collect(session, llm, profile(tool), library_a.id)
    [(data, output)] = seen
    assert isinstance(data, EchoInput) and data.keyword == "공룡"
    assert output == {"n": 3}


async def test_result_not_in_run_record(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] tool의 화면용 변환 / 실행 기록에 없음"""
    tool = Tool(
        "echo",
        "찾기",
        EchoInput,
        Recorder(result="결과"),
        "찾고 있어요",
        record_fields=("keyword",),
        present=lambda data, output: {"secret": SECRET},
    )
    llm = FakeLlm([tool_turn(call("echo", {"keyword": "a"})), answer_turn()])
    events = await collect(session, llm, profile(tool), library_a.id)
    assert results(events) == [{"secret": SECRET}]
    run_id = done(events).run_id
    row = await records.get_run(session, library_a.id, run_id)
    await session.refresh(row)
    steps = await records.list_steps(session, library_a.id, run_id)
    stored = str(row.answer_record) + str([(s.name, s.detail) for s in steps])
    assert SECRET not in stored
