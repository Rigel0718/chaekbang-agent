"""OpenAI Responses API 어댑터. 제공자 형식은 이 파일 밖으로 나가지 않는다.

store=False로 불러 대화를 제공자 쪽에 남기지 않는다. 그래서 이전 응답 id를 쓰지 않고,
응답의 output 항목(추론, tool 호출)을 다음 호출의 input에 그대로 이어 보낸다.
"""

import json
from typing import Any

import openai
from openai.types.responses import Response

from app.agent.llm import (
    AssistantMessage,
    Instruction,
    LlmError,
    LlmTurn,
    Message,
    Stop,
    ToolCall,
    ToolResult,
    Usage,
    UserMessage,
)
from app.agent.tools import ToolSpec
from app.core.config import Settings, get_settings

ERROR_PREFIX = "오류: "


def _tool(spec: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "name": spec.name,
        "description": spec.description,
        "parameters": spec.parameters,
        "strict": True,
    }


def _input(messages: list[Message]) -> list[Any]:
    items: list[Any] = []
    for message in messages:
        if isinstance(message, UserMessage):
            items.append({"role": "user", "content": message.text})
        elif isinstance(message, AssistantMessage):
            items.append({"role": "assistant", "content": message.text})
        elif isinstance(message, Instruction):
            items.append({"role": "developer", "content": message.text})
        elif isinstance(message, ToolResult):
            output = f"{ERROR_PREFIX}{message.content}" if message.is_error else message.content
            items.append(
                {"type": "function_call_output", "call_id": message.call_id, "output": output}
            )
        else:
            items.extend(message.raw)
    return items


def _arguments(text: str) -> Any:
    """파싱하지 못하면 None이고, 실행기가 형식 오류로 돌려준다."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _usage(response: Response) -> Usage:
    usage = response.usage
    if usage is None:
        return Usage()
    return Usage(
        input_tokens=usage.input_tokens,
        cached_input_tokens=usage.input_tokens_details.cached_tokens,
        cache_write_tokens=usage.input_tokens_details.cache_write_tokens,
        output_tokens=usage.output_tokens,
    )


def _refused(response: Response) -> bool:
    return any(
        part.type == "refusal"
        for item in response.output
        if item.type == "message"
        for part in item.content
    )


def _stop(response: Response, calls: tuple[ToolCall, ...]) -> Stop:
    if response.status == "failed":
        raise LlmError("response_failed")
    if response.status == "incomplete":
        details = response.incomplete_details
        return Stop.REFUSED if details and details.reason == "content_filter" else Stop.TRUNCATED
    if _refused(response):
        return Stop.REFUSED
    return Stop.TOOL_USE if calls else Stop.END


def to_turn(response: Response) -> LlmTurn:
    calls = tuple(
        ToolCall(item.call_id, item.name, _arguments(item.arguments))
        for item in response.output
        if item.type == "function_call"
    )
    return LlmTurn(
        stop=_stop(response, calls),
        tool_calls=calls,
        text=response.output_text or None,
        usage=_usage(response),
        raw=[item.model_dump(mode="json", exclude_none=True) for item in response.output],
    )


class OpenAiClient:
    def __init__(self, settings: Settings | None = None, client: Any = None) -> None:
        self.settings = settings or get_settings()
        self.model = self.settings.llm_model
        self._client = client

    def _sdk(self) -> Any:
        """키가 없어도 서버는 시작한다. 호출할 때 처음 만든다."""
        if self._client is None:
            key = self.settings.openai_api_key
            if key is None or not key.get_secret_value():
                raise LlmError("api_key_missing")
            self._client = openai.AsyncOpenAI(
                api_key=key.get_secret_value(), timeout=self.settings.llm_timeout_seconds
            )
        return self._client

    async def complete(
        self, *, system: str, tools: list[ToolSpec], messages: list[Message]
    ) -> LlmTurn:
        sdk = self._sdk()
        try:
            response = await sdk.responses.create(
                model=self.model,
                instructions=system,
                input=_input(messages),
                tools=[_tool(spec) for spec in tools],
                tool_choice="required",
                reasoning={"effort": self.settings.llm_effort},
                max_output_tokens=self.settings.llm_max_tokens,
                store=False,
            )
        except openai.OpenAIError as exc:
            # 오류 메시지에 요청 내용이 있을 수 있어 종류만 남긴다.
            raise LlmError(type(exc).__name__) from exc
        return to_turn(response)
