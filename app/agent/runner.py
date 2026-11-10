"""공통 실행기: tool 호출 루프, 최종 검사, 실행 기록. 어떤 tool이 있는지 모른다.

세션은 부르는 쪽이 넘긴다. 단계를 기록할 때마다 커밋해서 LLM 호출 동안 트랜잭션을 잡지 않는다.
tool과 검사는 이 세션 하나로 순서대로 돈다. 답은 검사를 통과한 뒤에만 사건으로 나간다.
"""

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Any

import anyio
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import records
from app.agent.llm import (
    AssistantMessage,
    Instruction,
    LlmClient,
    LlmError,
    LlmTurn,
    Message,
    Stop,
    ToolCall,
    ToolResult,
    UserMessage,
)
from app.agent.models import AgentRun, RunStatus, StepKind
from app.agent.profile import CheckContext, Profile, Violation
from app.agent.tools import Tool, ToolContext, ToolInput
from app.core.errors import DomainError

logger = logging.getLogger(__name__)

NAME_LENGTH = 100  # agent_steps.name
ANSWER_REQUIRED = "최종 답은 {tool} tool로만 낼 수 있습니다. {tool}을 호출하세요."
ANSWER_ALONE = "{tool}은 다른 tool과 함께 호출할 수 없습니다. 결과를 본 뒤 단독으로 호출하세요."
UNKNOWN_TOOL = "없는 tool입니다."
INVALID_INPUT = "입력이 형식에 맞지 않습니다: {detail}"


@dataclass(frozen=True)
class StatusEvent:
    text: str


@dataclass(frozen=True)
class AnswerEvent:
    answer: Any


@dataclass(frozen=True)
class DoneEvent:
    run_id: int
    status: RunStatus


RunEvent = StatusEvent | AnswerEvent | DoneEvent


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _content(result: Any) -> str:
    return (
        result if isinstance(result, str) else json.dumps(result, ensure_ascii=False, default=str)
    )


def _invalid(error: ValidationError) -> str:
    """입력 값을 빼고 위치와 이유만 쓴다."""
    parts = [
        f"{'.'.join(str(p) for p in e['loc']) or '입력'}: {e['msg']}"
        for e in error.errors(include_input=False, include_url=False, include_context=False)
    ]
    return INVALID_INPUT.format(detail="; ".join(parts))


class _Execution:
    def __init__(
        self,
        session: AsyncSession,
        llm: LlmClient,
        profile: Profile,
        library_id: int,
        user_text: str,
        history: Sequence[UserMessage | AssistantMessage],
    ) -> None:
        self.session = session
        self.llm = llm
        self.profile = profile
        self.library_id = library_id
        self.tools = {tool.name: tool for tool in profile.tools}
        self.specs = [tool.spec for tool in profile.tools] + [profile.answer_tool.spec]
        self.messages: list[Message] = [*history, UserMessage(user_text)]
        self.user_texts = tuple(m.text for m in self.messages if isinstance(m, UserMessage))
        self.tool_names: list[str] = []
        self.seq = 0
        self.input_tokens = 0
        self.cached_input_tokens = 0
        self.cache_write_tokens = 0
        self.output_tokens = 0
        self.record: AgentRun | None = None
        self.record_id: int | None = None  # rollback으로 record가 만료돼도 읽을 수 있게 둔다
        self.finished = False

    @property
    def run_id(self) -> int:
        assert self.record_id is not None
        return self.record_id

    async def start(self) -> None:
        self.record = await records.start_run(
            self.session,
            self.library_id,
            profile=self.profile.name,
            profile_version=self.profile.version,
            model=self.llm.model,
        )
        self.record_id = self.record.id

    async def step(self, kind: StepKind, started: float, **values: Any) -> None:
        self.seq += 1
        await records.add_step(
            self.session,
            self.library_id,
            self.run_id,
            self.seq,
            kind,
            duration_ms=_elapsed_ms(started),
            **values,
        )

    async def finish(self, status: RunStatus) -> None:
        assert self.record is not None
        await self.session.rollback()  # 끝나지 않은 tool 트랜잭션을 버린다
        await records.finish_run(
            self.session,
            self.record,
            status,
            input_tokens=self.input_tokens,
            cached_input_tokens=self.cached_input_tokens,
            cache_write_tokens=self.cache_write_tokens,
            output_tokens=self.output_tokens,
        )
        self.finished = True

    async def end(self, answer: Any, status: RunStatus) -> AsyncIterator[RunEvent]:
        """기록을 끝낸 뒤 내보낸다. 소비자가 답만 받고 멈춰도 중단으로 남지 않는다."""
        await self.finish(status)
        yield AnswerEvent(answer)
        yield DoneEvent(self.run_id, status)

    async def call_llm(self) -> LlmTurn | None:
        started = time.monotonic()
        try:
            turn = await self.llm.complete(
                system=self.profile.system_prompt, tools=self.specs, messages=list(self.messages)
            )
        except LlmError:
            await self.step(StepKind.LLM, started, is_error=True)
            return None
        self.input_tokens += turn.usage.input_tokens
        self.cached_input_tokens += turn.usage.cached_input_tokens
        self.cache_write_tokens += turn.usage.cache_write_tokens
        self.output_tokens += turn.usage.output_tokens
        failed = turn.stop in (Stop.REFUSED, Stop.TRUNCATED)
        await self.step(StepKind.LLM, started, is_error=failed)
        return turn

    async def reject_tool(self, call: ToolCall, message: str, tool: Tool | None) -> ToolResult:
        await self.step(
            StepKind.TOOL,
            time.monotonic(),
            name=(tool.name if tool else call.name)[:NAME_LENGTH],
            is_error=True,
        )
        return ToolResult(call.id, message, is_error=True)

    async def run_tool(self, tool: Tool, call: ToolCall, data: ToolInput) -> ToolResult:
        detail = (
            data.model_dump(mode="json", include=set(tool.record_fields))
            if tool.record_fields
            else None
        )
        started = time.monotonic()
        self.tool_names.append(tool.name)
        try:
            output = await tool.handler(ToolContext(self.library_id, self.session), data)
        except DomainError as exc:
            await self.session.rollback()
            await self.step(StepKind.TOOL, started, name=tool.name, is_error=True, detail=detail)
            return ToolResult(call.id, exc.message, is_error=True)
        except Exception:
            await self.session.rollback()
            await self.step(StepKind.TOOL, started, name=tool.name, is_error=True, detail=detail)
            raise
        await self.step(StepKind.TOOL, started, name=tool.name, detail=detail)
        return ToolResult(call.id, _content(output))

    async def run_calls(self, calls: Sequence[ToolCall]) -> AsyncIterator[RunEvent]:
        """요청 순서대로 실행하고 결과를 함께 돌려준다. 최종 답 tool은 실행하지 않는다."""
        answer_name = self.profile.answer_tool.name
        results: list[ToolResult] = []
        for call in calls:
            tool = self.tools.get(call.name)
            if call.name == answer_name:
                results.append(
                    await self.reject_tool(call, ANSWER_ALONE.format(tool=answer_name), None)
                )
            elif tool is None:
                results.append(await self.reject_tool(call, UNKNOWN_TOOL, None))
            else:
                try:
                    data = tool.input_model.model_validate(call.arguments)
                except ValidationError as exc:
                    results.append(await self.reject_tool(call, _invalid(exc), tool))
                    continue
                yield StatusEvent(tool.status_label)
                results.append(await self.run_tool(tool, call, data))
        self.messages.extend(results)

    async def check(self, answer: Any) -> list[Violation]:
        ctx = CheckContext(self.library_id, self.session, self.user_texts, tuple(self.tool_names))
        violations: list[Violation] = []
        for final_check in self.profile.final_checks:
            started = time.monotonic()
            found = await final_check.check(ctx, answer)
            items = [item for violation in found for item in violation.items]
            await self.step(
                StepKind.CHECK,
                started,
                name=final_check.name,
                is_error=bool(found),
                detail={"items": items} if found else None,
            )
            violations.extend(found)
        return violations

    async def repaired(self, answer: Any, violations: list[Violation]) -> Any | None:
        """위반 항목을 뺀 답이 검사를 통과하면 그 답이다."""
        if self.profile.repair is None:
            return None
        fixed = self.profile.repair(answer, violations)
        if fixed is None or await self.check(fixed):
            return None
        return fixed

    async def events(self) -> AsyncIterator[RunEvent]:
        profile = self.profile
        answer_tool = profile.answer_tool
        fallback = profile.fallback_answer
        reminded = False
        check_retries = 0
        for _ in range(profile.max_llm_calls):
            turn = await self.call_llm()
            if turn is None or turn.stop == Stop.TRUNCATED:
                async for event in self.end(fallback, RunStatus.FAILED):
                    yield event
                return
            if turn.stop == Stop.REFUSED:
                async for event in self.end(fallback, RunStatus.REFUSED):
                    yield event
                return
            self.messages.append(turn)

            if not turn.tool_calls:
                if reminded:
                    async for event in self.end(fallback, RunStatus.FALLBACK):
                        yield event
                    return
                reminded = True
                self.messages.append(Instruction(ANSWER_REQUIRED.format(tool=answer_tool.name)))
                continue

            if len(turn.tool_calls) > 1 or turn.tool_calls[0].name != answer_tool.name:
                async for event in self.run_calls(turn.tool_calls):
                    yield event
                continue

            call = turn.tool_calls[0]
            try:
                answer = answer_tool.input_model.model_validate(call.arguments)
            except ValidationError as exc:
                self.messages.append(ToolResult(call.id, _invalid(exc), is_error=True))
                continue

            violations = await self.check(answer)
            if not violations:
                async for event in self.end(answer, RunStatus.COMPLETED):
                    yield event
                return
            if check_retries < profile.max_check_retries:
                check_retries += 1
                message = "\n".join(v.message for v in violations)
                self.messages.append(ToolResult(call.id, message, is_error=True))
                continue

            fixed = await self.repaired(answer, violations)
            if fixed is not None:
                async for event in self.end(fixed, RunStatus.REPAIRED):
                    yield event
            else:
                async for event in self.end(fallback, RunStatus.FALLBACK):
                    yield event
            return

        async for event in self.end(fallback, RunStatus.FALLBACK):
            yield event


async def run(
    *,
    session: AsyncSession,
    llm: LlmClient,
    profile: Profile,
    library_id: int,
    user_text: str,
    history: Sequence[UserMessage | AssistantMessage] = (),
) -> AsyncIterator[RunEvent]:
    """library_id는 인증한 코드가 정한다. history는 이전 턴의 이용자 문장과 최종 답 글이다."""
    execution = _Execution(session, llm, profile, library_id, user_text, history)
    await execution.start()
    try:
        try:
            async for event in execution.events():
                yield event
        except Exception as exc:
            # 내용에 이용자 값이 있을 수 있어 종류만 남긴다.
            logger.error("agent run %s failed: %s", execution.run_id, type(exc).__name__)
            await execution.session.rollback()
            async for event in execution.end(profile.fallback_answer, RunStatus.FAILED):
                yield event
    finally:
        if not execution.finished:
            # 서버(anyio)의 취소는 await마다 다시 걸리므로 막아서 기록을 끝낸 뒤에 넘긴다.
            # 부르는 쪽이 같은 세션으로 이어서 정리할 수 있게 한다.
            with anyio.CancelScope(shield=True):
                await asyncio.shield(execution.finish(RunStatus.CANCELLED))
