"""[agent/runner] OpenAI 어댑터. 네트워크 없이 가짜 SDK 클라이언트로 요청과 응답 변환을 본다."""

from dataclasses import dataclass, field
from typing import Any

import httpx
import openai
import pytest
from openai.types.responses import Response
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import records
from app.agent.llm import (
    AssistantMessage,
    Instruction,
    LlmError,
    Stop,
    ToolCall,
    ToolResult,
    Usage,
    UserMessage,
)
from app.agent.models import RunStatus
from app.agent.openai_client import OpenAiClient, to_turn
from app.agent.runner import run
from app.agent.tools import ToolSpec
from app.core.config import Settings
from tests.agent.fakes import FALLBACK, answers, done, profile
from tests.conftest import Tenant

SPEC = ToolSpec("find", "찾기", {"type": "object", "additionalProperties": False})


def _settings(**values: Any) -> Settings:
    return Settings(_env_file=None, database_url="postgresql+asyncpg://unused", **values)


def _response(output: list[dict[str, Any]], **values: Any) -> Response:
    data: dict[str, Any] = {
        "id": "resp_1",
        "created_at": 1,
        "model": "gpt-6-luna",
        "object": "response",
        "output": output,
        "parallel_tool_calls": True,
        "tool_choice": "required",
        "tools": [],
        "status": "completed",
        "usage": {
            "input_tokens": 100,
            "input_tokens_details": {
                "cached_tokens": 40,
                "cache_write_tokens": 7,
            },
            "output_tokens": 10,
            "output_tokens_details": {"reasoning_tokens": 5},
            "total_tokens": 110,
        },
    }
    return Response.model_validate({**data, **values})


REASONING = {"id": "rs_1", "type": "reasoning", "summary": [], "encrypted_content": "enc"}
FUNCTION_CALL = {
    "id": "fc_1",
    "type": "function_call",
    "call_id": "call_1",
    "name": "find",
    "arguments": '{"keyword": "공룡"}',
    "status": "completed",
}


def _message(*content: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "status": "completed",
        "content": list(content),
    }


@dataclass
class _Responses:
    result: Any
    requests: list[dict[str, Any]] = field(default_factory=list)

    async def create(self, **values: Any) -> Any:
        self.requests.append(values)
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@dataclass
class _Sdk:
    responses: _Responses


def _client(result: Any, **settings: Any) -> tuple[OpenAiClient, _Responses]:
    responses = _Responses(result)
    return OpenAiClient(_settings(**settings), _Sdk(responses)), responses


async def test_request_values() -> None:
    """[agent/runner] 제공자 저장 없음 / 저장 끔"""
    client, responses = _client(_response([FUNCTION_CALL]))
    await client.complete(system="시스템", tools=[SPEC], messages=[UserMessage("공룡")])
    request = responses.requests[0]
    assert request["store"] is False
    assert "previous_response_id" not in request
    assert request["model"] == "gpt-6-luna"
    assert request["instructions"] == "시스템"
    assert request["tool_choice"] == "required"
    assert request["reasoning"] == {"effort": "low"}
    assert request["max_output_tokens"] == 25000
    assert "temperature" not in request
    assert request["tools"] == [
        {
            "type": "function",
            "name": "find",
            "description": "찾기",
            "parameters": SPEC.parameters,
            "strict": True,
        }
    ]


async def test_model_setting(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/runner] LLM 설정 / 모델 설정 적용"""
    answer = {**FUNCTION_CALL, "name": "submit", "arguments": '{"message": "답", "items": []}'}
    client, responses = _client(_response([answer]), llm_model="gpt-5-mini")
    events = [
        event
        async for event in run(
            session=session,
            llm=client,
            profile=profile(),
            library_id=library_a.id,
            user_text="책",
        )
    ]
    assert responses.requests[0]["model"] == "gpt-5-mini"
    row = await records.get_run(session, library_a.id, done(events).run_id)
    assert row.model == "gpt-5-mini"


async def test_run_without_api_key(
    session: AsyncSession, library_a: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[agent/runner] LLM 설정 / 키 없이 실행"""
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    events = [
        event
        async for event in run(
            session=session,
            llm=OpenAiClient(_settings()),
            profile=profile(),
            library_id=library_a.id,
            user_text="책",
        )
    ]
    assert answers(events) == [FALLBACK]
    assert done(events).status == RunStatus.FAILED


def test_key_is_not_in_settings_repr() -> None:
    """[agent/runner] LLM 설정 / 키 없이 서버 시작 (키 값은 출력에 남지 않는다)"""
    assert "sk-secret" not in repr(_settings(openai_api_key=SecretStr("sk-secret")))


async def test_messages_are_converted_in_order() -> None:
    """[agent/runner] 실행 안 대화 유지 / 응답 내용 재전송"""
    turn = to_turn(_response([REASONING, FUNCTION_CALL]))
    client, responses = _client(_response([FUNCTION_CALL]))
    await client.complete(
        system="s",
        tools=[SPEC],
        messages=[
            UserMessage("앞 질문"),
            AssistantMessage("앞 답"),
            UserMessage("이번 질문"),
            turn,
            ToolResult("call_1", "결과"),
            ToolResult("call_2", "없습니다", is_error=True),
            Instruction("지시"),
        ],
    )
    items = responses.requests[0]["input"]
    assert items[:3] == [
        {"role": "user", "content": "앞 질문"},
        {"role": "assistant", "content": "앞 답"},
        {"role": "user", "content": "이번 질문"},
    ]
    assert [item["type"] for item in items[3:5]] == ["reasoning", "function_call"]
    assert items[3]["encrypted_content"] == "enc"
    assert items[4]["call_id"] == "call_1"
    assert items[5:] == [
        {"type": "function_call_output", "call_id": "call_1", "output": "결과"},
        {"type": "function_call_output", "call_id": "call_2", "output": "오류: 없습니다"},
        {"role": "developer", "content": "지시"},
    ]


def test_tool_call_turn() -> None:
    """[agent/runner] 호출 루프 / tool을 거쳐 최종 답 (응답 변환)"""
    turn = to_turn(_response([REASONING, FUNCTION_CALL]))
    assert turn.stop == Stop.TOOL_USE
    assert turn.tool_calls == (ToolCall("call_1", "find", {"keyword": "공룡"}),)
    assert turn.usage == Usage(
        input_tokens=100, cached_input_tokens=40, cache_write_tokens=7, output_tokens=10
    )


def test_broken_arguments_become_none() -> None:
    """[agent/runner] 입력 검증 / 형식이 틀린 입력 (파싱하지 못한 입력)"""
    turn = to_turn(_response([{**FUNCTION_CALL, "arguments": '{"keyword": '}]))
    assert turn.tool_calls[0].arguments is None


def test_text_turn() -> None:
    """[agent/runner] 최종 답 tool / 글만 내고 끝남 (응답 변환)"""
    text = {"type": "output_text", "text": "안녕하세요", "annotations": []}
    turn = to_turn(_response([_message(text)]))
    assert (turn.stop, turn.text) == (Stop.END, "안녕하세요")


def test_refusal_item() -> None:
    """[agent/runner] LLM 오류 처리 / 응답 거절"""
    turn = to_turn(_response([_message({"type": "refusal", "refusal": "할 수 없어요"})]))
    assert turn.stop == Stop.REFUSED


def test_content_filter() -> None:
    """[agent/runner] LLM 오류 처리 / 응답 거절 (내용 필터)"""
    response = _response([], status="incomplete", incomplete_details={"reason": "content_filter"})
    assert to_turn(response).stop == Stop.REFUSED


def test_truncated() -> None:
    """[agent/runner] LLM 오류 처리 / 출력 잘림"""
    response = _response(
        [FUNCTION_CALL], status="incomplete", incomplete_details={"reason": "max_output_tokens"}
    )
    assert to_turn(response).stop == Stop.TRUNCATED


def test_failed_response() -> None:
    """[agent/runner] LLM 오류 처리 / LLM 호출 실패 (응답 상태 failed)"""
    with pytest.raises(LlmError):
        to_turn(_response([], status="failed"))


async def test_sdk_error_hides_details() -> None:
    """[agent/runner] LLM 오류 처리 / LLM 호출 실패"""
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    error = openai.APIConnectionError(message="이용자 문장이 든 메시지", request=request)
    client, _ = _client(error)
    with pytest.raises(LlmError) as caught:
        await client.complete(system="s", tools=[SPEC], messages=[UserMessage("공룡")])
    assert "이용자" not in str(caught.value)
