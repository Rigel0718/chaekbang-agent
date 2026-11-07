"""[agent/runner] 공통 실행기. 가짜 LLM과 가짜 tool만 쓴다."""

import asyncio

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.agent import records
from app.agent.llm import (
    AssistantMessage,
    Instruction,
    LlmTurn,
    Stop,
    ToolResult,
    Usage,
    UserMessage,
)
from app.agent.models import AgentRun, AgentStep, RunStatus, StepKind
from app.agent.runner import AnswerEvent, DoneEvent, StatusEvent, run
from app.agent.tools import AnswerTool, Tool, ToolInput
from app.core.errors import NotFoundError
from tests.agent.fakes import (
    FALLBACK,
    LLM_DOWN,
    NOT_FOUND,
    BookInput,
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
    statuses,
    text_turn,
    tool_turn,
)
from tests.conftest import Tenant


async def _run_row(session: AsyncSession, library_id: int, run_id: int) -> AgentRun:
    row = await records.get_run(session, library_id, run_id)
    await session.refresh(row)
    return row


async def _steps(session: AsyncSession, library_id: int, run_id: int) -> list[AgentStep]:
    return await records.list_steps(session, library_id, run_id)


# --- tool 정의 ---


async def test_llm_receives_tool_definitions(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] tool 정의 / LLM에 넘기는 tool 정의"""
    llm = FakeLlm([answer_turn()])
    await collect(session, llm, profile(echo_tool()), library_a.id)
    specs = {spec.name: spec for spec in llm.requests[0]["tools"]}
    assert set(specs) == {"echo", "submit"}
    echo = specs["echo"]
    assert echo.description == "찾기"
    assert echo.parameters["properties"]["keyword"]["type"] == "string"
    assert echo.parameters["additionalProperties"] is False
    assert echo.parameters["required"] == ["keyword"]


def test_tool_input_rejects_default_values() -> None:
    """[agent/runner] tool 정의 / LLM에 넘기는 tool 정의 (모든 필드가 필수)"""

    class Loose(ToolInput):
        keyword: str = "공룡"

    with pytest.raises(ValueError, match="keyword"):
        Tool("loose", "설명", Loose, Recorder(), "찾고 있어요")
    with pytest.raises(ValueError, match="keyword"):
        AnswerTool("loose", "설명", Loose)


def test_profile_rejects_duplicate_tool_names() -> None:
    """[agent/runner] 프로필의 tool만 실행 / 프로필에 없는 tool 호출 (이름은 겹치지 않는다)"""
    with pytest.raises(ValueError, match="겹칩니다"):
        profile(echo_tool(), echo_tool())


async def test_unknown_tool_is_not_executed(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 프로필의 tool만 실행 / 프로필에 없는 tool 호출"""
    handler = Recorder()
    llm = FakeLlm([tool_turn(call("drop_all", {})), answer_turn()])
    events = await collect(session, llm, profile(echo_tool(handler)), library_a.id)
    assert handler.calls == []
    result = llm.requests[1]["messages"][-1]
    assert isinstance(result, ToolResult) and result.is_error
    assert done(events).status == RunStatus.COMPLETED


async def test_invalid_input_is_not_executed(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 입력 검증 / 형식이 틀린 입력"""
    handler = Recorder()
    llm = FakeLlm([tool_turn(call("echo", {})), answer_turn()])
    await collect(session, llm, profile(echo_tool(handler)), library_a.id)
    assert handler.calls == []
    result = llm.requests[1]["messages"][-1]
    assert isinstance(result, ToolResult) and result.is_error
    assert "keyword" in result.content


async def test_unparsed_arguments_are_rejected(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 입력 검증 / 형식이 틀린 입력 (파싱하지 못한 입력)"""
    handler = Recorder()
    llm = FakeLlm([tool_turn(call("echo", None)), answer_turn()])
    await collect(session, llm, profile(echo_tool(handler)), library_a.id)
    assert handler.calls == []


async def test_invalid_answer_is_returned_to_llm(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 입력 검증 / 형식이 틀린 입력 (최종 답)"""
    llm = FakeLlm([tool_turn(call("submit", {"message": "답"})), answer_turn("고친 답")])
    events = await collect(session, llm, profile(), library_a.id)
    assert [a.message for a in answers(events)] == ["고친 답"]


async def test_library_is_injected(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 기관 범위 주입 / 실행 기관 전달"""
    handler = Recorder()
    llm = FakeLlm([tool_turn(call("echo", {"keyword": "공룡"})), answer_turn()])
    await collect(session, llm, profile(echo_tool(handler)), library_a.id)
    assert handler.calls == [(library_a.id, EchoInput(keyword="공룡"))]


async def test_llm_cannot_choose_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[agent/runner] 기관 범위 주입 / LLM이 기관을 넣은 입력"""
    handler = Recorder()
    arguments = {"keyword": "공룡", "library_id": library_b.id}
    llm = FakeLlm([tool_turn(call("echo", arguments)), answer_turn()])
    await collect(session, llm, profile(echo_tool(handler)), library_a.id)
    assert handler.calls == []
    result = llm.requests[1]["messages"][-1]
    assert isinstance(result, ToolResult) and result.is_error


# --- 호출 루프 ---


async def test_tool_then_answer(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 호출 루프 / tool을 거쳐 최종 답"""
    handler = Recorder(result={"title": "공룡 백과"})
    llm = FakeLlm([tool_turn(call("echo", {"keyword": "공룡"})), answer_turn("공룡 백과요")])
    events = await collect(session, llm, profile(echo_tool(handler)), library_a.id)
    assert len(handler.calls) == 1
    assert [a.message for a in answers(events)] == ["공룡 백과요"]
    result = llm.requests[1]["messages"][-1]
    assert result == ToolResult("c1", '{"title": "공룡 백과"}')


async def test_two_tools_in_one_turn(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 호출 루프 / 여러 tool 동시 요청"""
    first, second = Recorder(result="첫째"), Recorder(result="둘째")
    tools = (echo_tool(first, name="one"), echo_tool(second, name="two"))
    llm = FakeLlm(
        [
            tool_turn(
                call("one", {"keyword": "a"}, "c1"),
                call("two", {"keyword": "b"}, "c2"),
            ),
            answer_turn(),
        ]
    )
    await collect(session, llm, profile(*tools), library_a.id)
    assert llm.requests[1]["messages"][-2:] == [ToolResult("c1", "첫째"), ToolResult("c2", "둘째")]


async def test_history_comes_first(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 호출 루프 / 이전 대화 전달"""
    llm = FakeLlm([answer_turn()])
    history = [UserMessage("공룡 책 있어요?"), AssistantMessage("네, 있어요")]
    await collect(session, llm, profile(), library_a.id, user_text="더요", history=history)
    assert llm.requests[0]["messages"] == [*history, UserMessage("더요")]


# --- 최종 답 tool ---


async def test_answer_with_other_tool(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 최종 답 tool / 다른 tool과 함께 호출"""
    handler = Recorder()
    llm = FakeLlm(
        [
            tool_turn(
                call("echo", {"keyword": "a"}, "c1"),
                call("submit", {"message": "성급한 답", "items": []}, "c2"),
            ),
            answer_turn("나중 답"),
        ]
    )
    events = await collect(session, llm, profile(echo_tool(handler)), library_a.id)
    assert len(handler.calls) == 1
    assert [a.message for a in answers(events)] == ["나중 답"]
    result = llm.requests[1]["messages"][-1]
    assert result.call_id == "c2" and result.is_error


async def test_text_only_is_reminded(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 최종 답 tool / 글만 내고 끝남"""
    llm = FakeLlm([text_turn("해리 포터 어때요"), answer_turn("고친 답")])
    events = await collect(session, llm, profile(), library_a.id)
    assert isinstance(llm.requests[1]["messages"][-1], Instruction)
    assert [a.message for a in answers(events)] == ["고친 답"]
    assert "해리 포터" not in str(events)


async def test_text_only_twice_falls_back(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 최종 답 tool / 다시 요청해도 글만 냄"""
    llm = FakeLlm([text_turn(), text_turn()])
    events = await collect(session, llm, profile(), library_a.id)
    assert answers(events) == [FALLBACK]
    assert done(events).status == RunStatus.FALLBACK


# --- 최종 검사 ---


async def test_check_passes(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 최종 검사 / 검사 통과"""
    llm = FakeLlm([answer_turn(items=[1])])
    events = await collect(session, llm, profile(final_checks=(RejectIds({9}),)), library_a.id)
    assert answers(events)[0].items == [1]
    assert done(events).status == RunStatus.COMPLETED


async def test_violation_then_fixed(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 최종 검사 / 위반 후 고친 답"""
    llm = FakeLlm([answer_turn("나쁜 답", [9]), answer_turn("좋은 답", [1])])
    events = await collect(session, llm, profile(final_checks=(RejectIds({9}),)), library_a.id)
    assert [a.message for a in answers(events)] == ["좋은 답"]
    assert "나쁜 답" not in str(events)
    result = llm.requests[1]["messages"][-1]
    assert isinstance(result, ToolResult) and result.is_error
    assert result.content == "빼야 하는 항목입니다"


async def test_all_checks_run(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 최종 검사 / 위반 후 고친 답 (검사를 모두 돌린다)"""
    first, second = RejectIds({9}, "first"), RejectIds({8}, "second")
    llm = FakeLlm([answer_turn(items=[9, 8]), answer_turn(items=[1])])
    await collect(session, llm, profile(final_checks=(first, second)), library_a.id)
    assert len(first.seen) == len(second.seen) == 2
    assert llm.requests[1]["messages"][-1].content.count("빼야") == 2


async def test_no_checks(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 최종 검사 / 검사 없는 프로필"""
    llm = FakeLlm([answer_turn("그대로", [9])])
    events = await collect(session, llm, profile(), library_a.id)
    assert answers(events)[0].items == [9]
    assert done(events).status == RunStatus.COMPLETED


async def test_check_context(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 최종 검사 / 검사의 실행 정보"""
    check = RejectIds(set())
    llm = FakeLlm([tool_turn(call("echo", {"keyword": "a"})), answer_turn()])
    await collect(
        session,
        llm,
        profile(echo_tool(), final_checks=(check,)),
        library_a.id,
        user_text="더요",
        history=[UserMessage("7살 책"), AssistantMessage("네")],
    )
    ctx = check.seen[0]
    assert ctx.library_id == library_a.id
    assert ctx.user_texts == ("7살 책", "더요")
    assert ctx.tool_names == ("echo",)


async def test_failing_check_never_lets_answer_out(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/runner] 최종 검사 / 위반 후 고친 답 (검사가 죽으면 답은 나가지 않는다)"""

    class Broken:
        name = "broken"

        async def check(self, ctx, answer):
            raise RuntimeError("비밀 내용")

    llm = FakeLlm([answer_turn("나쁜 답")])
    events = await collect(session, llm, profile(final_checks=(Broken(),)), library_a.id)
    assert answers(events) == [FALLBACK]
    assert done(events).status == RunStatus.FAILED


async def test_repaired_answer(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 검사 재시도 초과 / 위반 항목을 빼고 통과"""
    prof = profile(final_checks=(RejectIds({9}),), repair=drop_items, max_check_retries=1)
    llm = FakeLlm([answer_turn(items=[9, 1]), answer_turn(items=[9, 2])])
    events = await collect(session, llm, prof, library_a.id)
    assert answers(events)[0].items == [2]
    assert done(events).status == RunStatus.REPAIRED
    assert len(llm.requests) == 2


async def test_repair_still_violates(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 검사 재시도 초과 / 정리해도 위반"""
    prof = profile(final_checks=(RejectIds({9}),), repair=lambda a, v: a, max_check_retries=0)
    events = await collect(session, FakeLlm([answer_turn(items=[9])]), prof, library_a.id)
    assert answers(events) == [FALLBACK]
    assert done(events).status == RunStatus.FALLBACK


async def test_no_repair_rule(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 검사 재시도 초과 / 정리 규칙 없음"""
    prof = profile(final_checks=(RejectIds({9}),), max_check_retries=0)
    events = await collect(session, FakeLlm([answer_turn(items=[9])]), prof, library_a.id)
    assert answers(events) == [FALLBACK]
    assert done(events).status == RunStatus.FALLBACK


# --- 한도와 오류 ---


async def test_llm_call_limit(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 실행 한도 / 호출 한도 초과"""
    script = [tool_turn(call("echo", {"keyword": "a"})) for _ in range(5)]
    llm = FakeLlm(script)
    events = await collect(session, llm, profile(echo_tool(), max_llm_calls=3), library_a.id)
    assert len(llm.requests) == 3
    assert answers(events) == [FALLBACK]
    assert done(events).status == RunStatus.FALLBACK


async def test_domain_error_goes_back_to_llm(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] tool 오류 처리 / 도메인 오류"""
    llm = FakeLlm([tool_turn(call("echo", {"keyword": "a"})), answer_turn("없어요")])
    events = await collect(
        session, llm, profile(echo_tool(Recorder(error=NOT_FOUND))), library_a.id
    )
    assert llm.requests[1]["messages"][-1] == ToolResult("c1", NOT_FOUND.message, is_error=True)
    assert done(events).status == RunStatus.COMPLETED


async def test_unexpected_error_fails_run(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] tool 오류 처리 / 예상하지 못한 예외"""
    boom = Recorder(error=RuntimeError("비밀 내용 01012345678"))
    llm = FakeLlm([tool_turn(call("echo", {"keyword": "a"}))])
    events = await collect(session, llm, profile(echo_tool(boom)), library_a.id)
    assert answers(events) == [FALLBACK]
    assert done(events).status == RunStatus.FAILED
    assert "비밀" not in str(events)
    steps = await _steps(session, library_a.id, done(events).run_id)
    assert "비밀" not in str([(s.name, s.detail) for s in steps])
    assert steps[-1].is_error


async def test_llm_failure(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] LLM 오류 처리 / LLM 호출 실패"""
    events = await collect(session, FakeLlm([LLM_DOWN]), profile(), library_a.id)
    assert answers(events) == [FALLBACK]
    assert done(events).status == RunStatus.FAILED


async def test_llm_refusal(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] LLM 오류 처리 / 응답 거절"""
    events = await collect(session, FakeLlm([LlmTurn(Stop.REFUSED)]), profile(), library_a.id)
    assert answers(events) == [FALLBACK]
    assert done(events).status == RunStatus.REFUSED


async def test_truncated_output(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] LLM 오류 처리 / 출력 잘림"""
    handler = Recorder()
    cut = LlmTurn(Stop.TRUNCATED, (call("echo", {"keyword": "a"}),))
    events = await collect(session, FakeLlm([cut]), profile(echo_tool(handler)), library_a.id)
    assert handler.calls == []
    assert answers(events) == [FALLBACK]
    assert done(events).status == RunStatus.FAILED


# --- 사건과 중단 ---


async def test_event_order(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 진행 사건 / 사건 순서"""
    llm = FakeLlm([tool_turn(call("echo", {"keyword": "비밀 검색어"})), answer_turn()])
    events = await collect(session, llm, profile(echo_tool()), library_a.id)
    assert [type(e) for e in events] == [StatusEvent, AnswerEvent, DoneEvent]
    assert statuses(events) == ["찾고 있어요"]
    assert "비밀 검색어" not in str(events)


async def test_rejected_answer_is_not_an_event(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 진행 사건 / 위반한 답은 사건에 없음"""
    llm = FakeLlm([answer_turn("나쁜 답", [9]), answer_turn("좋은 답", [1])])
    events = await collect(session, llm, profile(final_checks=(RejectIds({9}),)), library_a.id)
    assert [type(e) for e in events] == [AnswerEvent, DoneEvent]
    assert answers(events)[0].message == "좋은 답"


async def test_consumer_stops(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 중단 / 소비자가 중단"""
    llm = FakeLlm([tool_turn(call("echo", {"keyword": "a"})), answer_turn()])
    handler = Recorder()
    stream = run(
        session=session,
        llm=llm,
        profile=profile(echo_tool(handler)),
        library_id=library_a.id,
        user_text="책",
    )
    assert isinstance(await anext(stream), StatusEvent)
    await stream.aclose()
    assert handler.calls == []
    assert len(llm.requests) == 1
    row = await session.scalar(select(AgentRun).where(AgentRun.library_id == library_a.id))
    assert row is not None
    assert row.status == RunStatus.CANCELLED and row.finished_at is not None


async def test_task_cancelled(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 중단 / 소비자가 중단 (태스크 취소)"""
    entered = asyncio.Event()

    class Hanging(FakeLlm):
        async def complete(self, **values):
            entered.set()
            await asyncio.sleep(60)
            raise AssertionError

    async def consume() -> None:
        stream = run(
            session=session,
            llm=Hanging([]),
            profile=profile(),
            library_id=library_a.id,
            user_text="책",
        )
        async for _ in stream:
            pass

    task = asyncio.create_task(consume())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    row = await session.scalar(select(AgentRun).where(AgentRun.library_id == library_a.id))
    assert row is not None and row.status == RunStatus.CANCELLED


async def test_consumer_stops_after_answer_is_not_cancelled(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/runner] 중단 / 소비자가 중단 (답을 받은 뒤는 중단이 아니다)"""
    stream = run(
        session=session,
        llm=FakeLlm([answer_turn()]),
        profile=profile(),
        library_id=library_a.id,
        user_text="책",
    )
    assert isinstance(await anext(stream), AnswerEvent)
    await stream.aclose()
    row = await session.scalar(select(AgentRun).where(AgentRun.library_id == library_a.id))
    assert row is not None and row.status == RunStatus.COMPLETED


# --- 기록 ---


async def test_run_record(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 실행 기록 / 성공한 실행의 기록"""
    usage = Usage(input_tokens=100, cached_input_tokens=40, cache_write_tokens=7, output_tokens=10)
    llm = FakeLlm(
        [
            tool_turn(call("echo", {"keyword": "a"}), usage=usage),
            tool_turn(call("submit", {"message": "답", "items": []}, "answer"), usage=usage),
        ]
    )
    prof = profile(echo_tool(), final_checks=(RejectIds({9}),))
    events = await collect(session, llm, prof, library_a.id)
    run_id = done(events).run_id
    row = await _run_row(session, library_a.id, run_id)
    assert row.status == RunStatus.COMPLETED
    assert (row.profile, row.profile_version, row.model) == ("test", "v1", "fake-model")
    assert row.input_tokens == 200
    assert row.cached_input_tokens == 80
    assert row.cache_write_tokens == 14
    assert row.output_tokens == 20
    assert row.started_at is not None and row.finished_at is not None
    steps = await _steps(session, library_a.id, run_id)
    assert [(s.seq, s.kind, s.name) for s in steps] == [
        (1, StepKind.LLM, None),
        (2, StepKind.TOOL, "echo"),
        (3, StepKind.LLM, None),
        (4, StepKind.CHECK, "banned"),
    ]
    assert all(s.duration_ms >= 0 and not s.is_error for s in steps)


async def test_violation_record(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 실행 기록 / 위반 기록"""
    llm = FakeLlm([answer_turn("나쁜 답", [9]), answer_turn(items=[1])])
    events = await collect(session, llm, profile(final_checks=(RejectIds({9}),)), library_a.id)
    steps = await _steps(session, library_a.id, done(events).run_id)
    check = next(s for s in steps if s.kind == StepKind.CHECK)
    assert (check.name, check.is_error, check.detail) == ("banned", True, {"items": [9]})


async def test_running_record_is_committed(engine: AsyncEngine) -> None:
    """[agent/runner] 실행 기록 / 진행 중 기록

    다른 연결에서 봐야 해서 테스트 세션이 아니라 실제로 커밋하는 세션을 쓰고 행을 지운다.
    """
    maker = async_sessionmaker(engine, expire_on_commit=False)
    seen: dict[str, object] = {}

    async with maker() as setup:
        library_id = await setup.scalar(
            text(
                "INSERT INTO libraries (name, type, loan_mode)"
                " VALUES ('실행 기록 시험 기관', 'small_library', 'internal') RETURNING id"
            )
        )
        await setup.commit()

    async def handler(ctx, data):
        async with maker() as other:
            seen["status"] = await other.scalar(
                select(AgentRun.status).where(AgentRun.library_id == library_id)
            )
            seen["steps"] = list(
                await other.scalars(
                    select(AgentStep.kind).where(AgentStep.library_id == library_id)
                )
            )
        return "결과"

    try:
        async with maker() as session:
            llm = FakeLlm([tool_turn(call("echo", {"keyword": "a"})), answer_turn()])
            await collect(session, llm, profile(echo_tool(handler)), library_id)
        assert seen == {"status": RunStatus.RUNNING, "steps": [StepKind.LLM]}
    finally:
        async with maker() as cleanup:
            await cleanup.execute(delete(AgentStep).where(AgentStep.library_id == library_id))
            await cleanup.execute(delete(AgentRun).where(AgentRun.library_id == library_id))
            await cleanup.execute(text("DELETE FROM libraries WHERE id = :id"), {"id": library_id})
            await cleanup.commit()


async def test_no_raw_text_in_records(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 기록의 개인정보 / 원문이 저장되지 않음"""
    llm = FakeLlm(
        [tool_turn(call("echo", {"keyword": "회원 M0042"})), answer_turn("모델이 쓴 답 글")]
    )
    handler = Recorder(result="소개 문구입니다")
    events = await collect(
        session, llm, profile(echo_tool(handler)), library_a.id, user_text="회원번호 M0042예요"
    )
    run_id = done(events).run_id
    runs = await session.execute(text("SELECT * FROM agent_runs WHERE id = :i"), {"i": run_id})
    steps = await session.execute(
        text("SELECT * FROM agent_steps WHERE run_id = :i"), {"i": run_id}
    )
    stored = str(runs.mappings().all()) + str(steps.mappings().all())
    for value in ("M0042", "소개 문구", "모델이 쓴 답"):
        assert value not in stored


async def test_selected_input_is_recorded(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 기록의 개인정보 / 입력 기록을 고른 tool"""
    tool = Tool("find", "찾기", BookInput, Recorder(), "찾고 있어요", record_fields=("keywords",))
    arguments = {"keywords": ["공룡"], "member_number": "M0042"}
    llm = FakeLlm([tool_turn(call("find", arguments)), answer_turn()])
    events = await collect(session, llm, profile(tool), library_a.id)
    steps = await _steps(session, library_a.id, done(events).run_id)
    assert next(s for s in steps if s.kind == StepKind.TOOL).detail == {"keywords": ["공룡"]}


async def test_input_is_not_recorded_by_default(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 기록의 개인정보 / 입력 기록을 고르지 않은 tool"""
    llm = FakeLlm([tool_turn(call("echo", {"keyword": "공룡"})), answer_turn()])
    events = await collect(session, llm, profile(echo_tool()), library_a.id)
    steps = await _steps(session, library_a.id, done(events).run_id)
    assert next(s for s in steps if s.kind == StepKind.TOOL).detail is None


async def test_other_library_cannot_read_run(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[agent/runner] 기록의 기관 범위 / 다른 기관의 실행 조회"""
    events = await collect(session, FakeLlm([answer_turn()]), profile(), library_a.id)
    run_id = done(events).run_id
    with pytest.raises(NotFoundError):
        await records.get_run(session, library_b.id, run_id)
    with pytest.raises(NotFoundError):
        await records.list_steps(session, library_b.id, run_id)


async def test_no_transaction_during_llm_call(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 외부 호출 중 트랜잭션 없음 / LLM 호출 시점"""

    async def reads_db(ctx, data):
        await ctx.session.execute(text("SELECT 1"))
        return "결과"

    llm = FakeLlm(
        [tool_turn(call("echo", {"keyword": "a"})), answer_turn("나쁜 답", [9]), answer_turn()],
        session=session,
    )
    prof = profile(echo_tool(reads_db), final_checks=(RejectIds({9}),))
    await collect(session, llm, prof, library_a.id)
    assert llm.in_transaction == [False, False, False]


async def test_response_is_replayed_unchanged(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] 실행 안 대화 유지 / 응답 내용 재전송"""
    raw = [{"type": "reasoning", "encrypted_content": "x"}, {"type": "function_call"}]
    first = tool_turn(call("echo", {"keyword": "a"}), raw=raw)
    llm = FakeLlm([first, answer_turn()])
    await collect(session, llm, profile(echo_tool()), library_a.id)
    messages = llm.requests[1]["messages"]
    assert messages[1] is first and messages[1].raw is raw
    assert llm.requests[0]["system"] == llm.requests[1]["system"]
    assert llm.requests[0]["tools"] == llm.requests[1]["tools"]
