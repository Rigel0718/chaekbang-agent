"""AI 사서 대화 API 테스트 도우미: 가짜 LLM 끼우기, SSE 읽기."""

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest
from httpx import AsyncClient, Response

from app.library.api.librarian import get_llm, get_query_encoder
from app.main import app
from tests.agent.fakes import FakeLlm


@dataclass
class LlmSlot:
    """테스트가 응답을 정해 두는 가짜 LLM 자리. 비어 있으면 호출될 때 실패한다."""

    llm: FakeLlm

    def script(self, *turns: Any) -> FakeLlm:
        self.llm = FakeLlm(list(turns))
        return self.llm

    @property
    def calls(self) -> int:
        return len(self.llm.requests)


@pytest.fixture
async def fake_llm(_app: None) -> AsyncIterator[LlmSlot]:
    slot = LlmSlot(FakeLlm([]))
    app.dependency_overrides[get_llm] = lambda: slot.llm
    # 임베딩 서버를 부르지 않는다. 인코더를 넘기는 테스트는 따로 덮어쓴다
    app.dependency_overrides[get_query_encoder] = lambda: None
    yield slot
    app.dependency_overrides.pop(get_llm, None)
    app.dependency_overrides.pop(get_query_encoder, None)


@dataclass(frozen=True)
class Sse:
    name: str
    data: dict[str, Any]


def parse_sse(text: str) -> list[Sse]:
    events = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append(Sse(fields["event"], json.loads(fields["data"])))
    return events


async def send(client: AsyncClient, message: str, session_id: str | None = None) -> Response:
    body: dict[str, Any] = {"message": message}
    if session_id is not None:
        body["session_id"] = session_id
    return await client.post("/librarian/messages", json=body)


async def talk(client: AsyncClient, message: str, session_id: str | None = None) -> list[Sse]:
    res = await send(client, message, session_id)
    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("text/event-stream")
    return parse_sse(res.text)


def event(events: list[Sse], name: str) -> dict[str, Any]:
    [found] = [e.data for e in events if e.name == name]
    return found
