"""LLM 접점. 실행기는 제공자를 모른다. 제공자 형식은 어댑터가 바꾼다."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol

from app.agent.tools import ToolSpec


class LlmError(Exception):
    """LLM을 부를 수 없다. 메시지에 요청 내용이나 키를 넣지 않는다."""


class Stop(StrEnum):
    END = "end"
    TOOL_USE = "tool_use"
    REFUSED = "refused"
    TRUNCATED = "truncated"


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: Any  # 파싱한 입력. 파싱하지 못했으면 None이다


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0  # 캐시 입력을 포함한다
    cached_input_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class LlmTurn:
    stop: Stop
    tool_calls: tuple[ToolCall, ...] = ()
    text: str | None = None
    usage: Usage = field(default_factory=Usage)
    raw: Any = None  # 어댑터만 아는 응답 항목. 고치지 않고 다음 호출에 그대로 보낸다


@dataclass(frozen=True)
class UserMessage:
    text: str


@dataclass(frozen=True)
class AssistantMessage:
    """이전 턴의 최종 답 글."""

    text: str


@dataclass(frozen=True)
class Instruction:
    """실행기가 LLM에 주는 지시. 이용자 문장이 아니다."""

    text: str


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    content: str
    is_error: bool = False


Message = UserMessage | AssistantMessage | Instruction | ToolResult | LlmTurn


class LlmClient(Protocol):
    model: str

    async def complete(
        self, *, system: str, tools: list[ToolSpec], messages: list[Message]
    ) -> LlmTurn: ...
