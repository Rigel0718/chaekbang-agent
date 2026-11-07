"""가짜 LLM과 가짜 tool. 네트워크와 기관 패키지 없이 실행기를 돌린다."""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import LlmError, LlmTurn, Message, Stop, ToolCall, Usage
from app.agent.profile import CheckContext, Profile, Violation
from app.agent.runner import AnswerEvent, DoneEvent, RunEvent, StatusEvent, run
from app.agent.tools import AnswerTool, Tool, ToolContext, ToolInput, ToolSpec
from app.core.errors import NotFoundError


class EchoInput(ToolInput):
    keyword: str


class BookInput(ToolInput):
    keywords: list[str]
    member_number: str | None


class Answer(ToolInput):
    message: str
    items: list[int] = Field(min_length=0)


FALLBACK = Answer(message="지금은 답할 수 없습니다", items=[])
ANSWER_TOOL = AnswerTool("submit", "최종 답", Answer)


def call(name: str, arguments: Any, id: str = "c1") -> ToolCall:
    return ToolCall(id, name, arguments)


def tool_turn(*calls: ToolCall, usage: Usage | None = None, raw: Any = None) -> LlmTurn:
    return LlmTurn(Stop.TOOL_USE, calls, usage=usage or Usage(), raw=raw)


def answer_turn(message: str = "답", items: Sequence[int] = ()) -> LlmTurn:
    return tool_turn(call("submit", {"message": message, "items": list(items)}, "answer"))


def text_turn(text: str = "글만 쓴 답") -> LlmTurn:
    return LlmTurn(Stop.END, text=text)


@dataclass
class FakeLlm:
    """정해 둔 응답을 차례로 돌려주고 받은 요청을 남긴다."""

    script: list[LlmTurn | Exception]
    model: str = "fake-model"
    session: AsyncSession | None = None
    requests: list[dict[str, Any]] = field(default_factory=list)
    in_transaction: list[bool] = field(default_factory=list)

    async def complete(
        self, *, system: str, tools: list[ToolSpec], messages: list[Message]
    ) -> LlmTurn:
        self.requests.append({"system": system, "tools": tools, "messages": list(messages)})
        if self.session is not None:
            self.in_transaction.append(self.session.in_transaction())
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


@dataclass
class Recorder:
    """tool 호출을 남기는 실행 함수."""

    calls: list[tuple[int, Any]] = field(default_factory=list)
    result: Any = "결과"
    error: Exception | None = None

    async def __call__(self, ctx: ToolContext, data: Any) -> Any:
        self.calls.append((ctx.library_id, data))
        if self.error is not None:
            raise self.error
        return self.result


def echo_tool(handler: Any = None, *, name: str = "echo") -> Tool:
    return Tool(name, "찾기", EchoInput, handler or Recorder(), "찾고 있어요")


@dataclass
class RejectIds:
    """정해 둔 항목이 답에 있으면 위반이다."""

    banned: set[int]
    name: str = "banned"
    seen: list[CheckContext] = field(default_factory=list)

    async def check(self, ctx: CheckContext, answer: Answer) -> list[Violation]:
        self.seen.append(ctx)
        found = tuple(i for i in answer.items if i in self.banned)
        return [Violation("빼야 하는 항목입니다", found)] if found else []


def drop_items(answer: Answer, violations: Sequence[Violation]) -> Answer | None:
    banned = {item for v in violations for item in v.items}
    return answer.model_copy(update={"items": [i for i in answer.items if i not in banned]})


def profile(*tools: Tool, **values: Any) -> Profile:
    return Profile(
        name="test",
        version="v1",
        system_prompt="너는 시험용이다",
        tools=tools,
        answer_tool=ANSWER_TOOL,
        fallback_answer=FALLBACK,
        **values,
    )


async def collect(
    session: AsyncSession, llm: FakeLlm, prof: Profile, library_id: int, **values: Any
) -> list[RunEvent]:
    values.setdefault("user_text", "공룡 책 찾아 줘")
    return [
        event
        async for event in run(
            session=session, llm=llm, profile=prof, library_id=library_id, **values
        )
    ]


def answers(events: list[RunEvent]) -> list[Any]:
    return [e.answer for e in events if isinstance(e, AnswerEvent)]


def statuses(events: list[RunEvent]) -> list[str]:
    return [e.text for e in events if isinstance(e, StatusEvent)]


def done(events: list[RunEvent]) -> DoneEvent:
    last = events[-1]
    assert isinstance(last, DoneEvent)
    return last


NOT_FOUND = NotFoundError("찾을 수 없습니다")
LLM_DOWN = LlmError("RateLimitError")
