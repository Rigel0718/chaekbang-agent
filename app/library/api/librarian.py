"""AI 사서 대화 API. 키오스크와 관리자 모두 쓸 수 있다. 로직은 services/chat.py에 있다.

프로필과 LLM은 `app/main.py`가 `app.state`에 둔다. 프로필은 기관의 운영 방식으로 고른다.
"""

import json
import uuid
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import StreamingResponse

from app.agent.llm import LlmClient
from app.agent.openai_client import OpenAiClient
from app.library.deps import CurrentStaff, Session
from app.library.librarian import PROFILE_NAME
from app.library.schemas.librarian import MessageRequest
from app.library.services import chat

router = APIRouter(prefix="/librarian", tags=["librarian"])


def get_llm(request: Request) -> LlmClient:
    """키가 없어도 서버는 시작한다. 처음 부를 때 만든다."""
    llm = getattr(request.app.state, "librarian_llm", None)
    if llm is None:
        llm = request.app.state.librarian_llm = OpenAiClient()
    return llm


Llm = Annotated[LlmClient, Depends(get_llm)]


def _sse(event: chat.ServerEvent) -> str:
    return f"event: {event.name}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"


async def _encode(events: AsyncIterator[chat.ServerEvent]) -> AsyncIterator[str]:
    async for event in events:
        yield _sse(event)


@router.post(
    "/messages",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
)
async def post_message(
    data: MessageRequest, staff: CurrentStaff, session: Session, request: Request, llm: Llm
) -> StreamingResponse:
    """SSE로 `session`, `status`, `answer`, `done` 사건을 보낸다. 세션 id가 없으면 새 대화다."""
    prepared = await chat.prepare_turn(
        session, staff.library_id, data.session_id, data.message, profile_name=PROFILE_NAME
    )
    profile = request.app.state.librarian_profiles[prepared.loan_mode]
    return StreamingResponse(
        _encode(chat.stream_turn(session, llm, profile, prepared)),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store"},
    )


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(session_id: uuid.UUID, staff: CurrentStaff, session: Session) -> Response:
    await chat.end_session(session, staff.library_id, session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
