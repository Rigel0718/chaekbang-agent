"""운영 에이전트 대화 service. 세션 열기·가리기·상한·처리 중 표시는 AI 사서 대화
(`services/chat.py`)의 함수를 그대로 쓰고, 세션 종류만 `admin`이다.

확인(`prepare_admin_turn`)은 응답을 시작하기 전에 끝낸다(404, 409, 429). 그 뒤
(`stream_admin_turn`)는 SSE 사건 `session`, `status`, `result`(0개 이상), `answer`, `done`이다.
답에는 문장과 못 하는 분석의 종류(`unsupported`)가 있고, 찾은 책·카드·노출 기록은 없다.
`result`는 tool이 고른 화면용 값(표·초안 링크, `schemas/admin_results.py`)이고 실행기가 답 바로
앞에 낸다. `chat_messages`에는 가린 질문과 최종 답 문장만 두고 `result`는 남기지 않는다. 못 하는
분석의 종류는 실행 행에 남는다(최종 답의 기록 필드).
"""

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import anyio
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import LlmClient
from app.agent.profile import Profile
from app.agent.runner import AnswerEvent, DoneEvent, ResultEvent, StatusEvent, run
from app.central.embedding import Embedder
from app.library.models.chat import ChatMessage, ChatRole, SessionKind
from app.library.privacy import mask_personal
from app.library.schemas.admin_agent import AdminAnswerPayload
from app.library.services.chat import (
    PreparedTurn,
    ServerEvent,
    check_daily_limit,
    load_history,
    open_session,
    purge_expired,
    release,
)
from app.library.services.topic import QUERY_ENCODER

KIND = SessionKind.ADMIN


async def prepare_admin_turn(
    session: AsyncSession,
    library_id: int,
    session_id: uuid.UUID | None,
    text: str,
    *,
    profile_name: str,
) -> PreparedTurn:
    """응답을 시작하기 전의 확인. 실패하면 LLM은 호출되지 않고 세션과 메시지도 만들지 않는다."""
    await purge_expired(session, library_id)
    await check_daily_limit(session, library_id, profile_name, KIND)
    chat, loan_mode = await open_session(session, library_id, session_id, KIND)
    history = await load_history(session, library_id, chat.id)
    masked = await mask_personal(session, library_id, text)
    session.add(
        ChatMessage(library_id=library_id, session_id=chat.id, role=ChatRole.USER, content=masked)
    )
    await session.commit()
    return PreparedTurn(library_id, chat.id, loan_mode, masked, history)


async def _finish(
    session: AsyncSession, prepared: PreparedTurn, answer: Any, done: DoneEvent
) -> list[ServerEvent]:
    session.add(
        ChatMessage(
            library_id=prepared.library_id,
            session_id=prepared.session_id,
            role=ChatRole.ASSISTANT,
            content=answer.message,
        )
    )
    await session.commit()
    payload = AdminAnswerPayload(message=answer.message, unsupported=answer.unsupported)
    return [
        ServerEvent("answer", payload.model_dump(mode="json")),
        ServerEvent("done", {"run_id": done.run_id, "status": done.status.value}),
    ]


async def stream_admin_turn(
    session: AsyncSession,
    llm: LlmClient,
    profile: Profile,
    prepared: PreparedTurn,
    encoder: Embedder | None = None,
) -> AsyncIterator[ServerEvent]:
    """진행 사건은 바로 보내고, 답은 실행이 끝난 뒤 보낸다. 끝나거나 끊기면 표시를 푼다.

    질의 인코더는 소장 도서 검색 tool의 벡터 질의에 쓴다(실행 값). 없으면 키워드 순위로 내려간다.
    """
    assert prepared.user_text is not None
    events = run(
        session=session,
        llm=llm,
        profile=profile,
        library_id=prepared.library_id,
        user_text=prepared.user_text,
        history=prepared.history,
        tool_values={QUERY_ENCODER: encoder},
    )
    try:
        yield ServerEvent("session", {"session_id": str(prepared.session_id)})
        answer: Any = None
        async for event in events:
            if isinstance(event, StatusEvent):
                yield ServerEvent("status", {"text": event.text})
            elif isinstance(event, ResultEvent):
                yield ServerEvent("result", event.value.model_dump(mode="json"))
            elif isinstance(event, AnswerEvent):
                answer = event.answer
            elif isinstance(event, DoneEvent):
                for server_event in await _finish(session, prepared, answer, event):
                    yield server_event
    finally:

        async def cleanup() -> None:
            await events.aclose()
            await release(session, prepared.library_id, prepared.session_id)

        with anyio.CancelScope(shield=True):
            await asyncio.shield(cleanup())
