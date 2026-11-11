"""AI 사서 대화 service. 세션, 상한, 개인정보 가리기, 실행, 카드, 저장, 노출 기록의 순서를 맡는다.

확인(`prepare_turn`)은 응답을 시작하기 전에 끝내서 404, 409, 422, 429를 일반 HTTP 응답으로 돌려준다.
그 뒤(`stream_turn`)는 SSE 사건이다. 답은 검사를 통과한 뒤에 한 번에 나간다.

대화는 진행 중에만 둔다. 끝난 세션은 서버의 주기 작업과 요청 처리 때 지운다. `chat_messages`에는
가린 이용자 문장과 최종 답만 두고, tool 입력과 결과, 검사를 통과하지 못한 답은 저장하지 않는다.

검색과 잇기: 자동완성에서 고른 책(`selected_library_book_id`)이나 문장 속 서명으로 찾은 책은
LLM보다 먼저 `found` 사건으로 보낸다. 고른 책만 보낸 턴은 LLM을 부르지 않는다. 책 표시
(`[고른 책: #12 데미안]`)는 이용자 문장과 따로 `note`에 두고 LLM에게는 코드의 안내로 보낸다.
서명의 "아이" 같은 낱말이 어린이 요청 판단에 섞이지 않게 하기 위해서다.
"""

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import anyio
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import AssistantMessage, Instruction, LlmClient, UserMessage
from app.agent.models import AgentRun
from app.agent.profile import Profile
from app.agent.runner import AnswerEvent, DoneEvent, StatusEvent, run
from app.core import clock
from app.core.config import get_settings
from app.core.errors import ConflictError, LimitExceededError, NotFoundError
from app.library.models.chat import ChatMessage, ChatRole, ChatSession
from app.library.models.library import Library, LoanMode
from app.library.privacy import mask_personal
from app.library.recommendation.cards import build_cards, build_summaries
from app.library.recommendation.events import add_events
from app.library.recommendation.lookup import found_in_text, get_findable
from app.library.recommendation.search import Candidate
from app.library.schemas.catalog import BookSummary
from app.library.schemas.librarian import AnswerPayload, BookCard

logger = logging.getLogger(__name__)

# 서버가 죽어 처리 중 표시가 남아도 이 시간이 지나면 다시 쓸 수 있다.
BUSY_TIMEOUT = timedelta(minutes=3)
BOOKS_NOTE = "[추천한 책: {books}]"
SELECTED_NOTE = "[고른 책: {books}]"
FOUND_NOTE = "[찾은 책: {books}]"
SELECTED_STATUS = "selected"  # 고른 책만 보낸 턴의 done 상태. 실행이 없어 run_id는 null이다

History = tuple[UserMessage | AssistantMessage | Instruction, ...]


@dataclass(frozen=True)
class ServerEvent:
    name: str  # session, found, status, answer, done
    data: dict[str, Any]


@dataclass(frozen=True)
class PreparedTurn:
    library_id: int
    session_id: uuid.UUID
    loan_mode: LoanMode
    user_text: str | None  # 가린 문장. 고른 책만 보낸 턴은 None이고 LLM을 부르지 않는다
    history: History
    note: str | None = None  # 이번 턴의 책 표시. LLM에게는 이용자 문장 바로 앞의 안내로 간다
    found: tuple[BookSummary, ...] = ()  # 고른 책이나 문장 속 서명으로 찾은 책


def _idle() -> timedelta:
    return timedelta(minutes=get_settings().librarian_session_idle_minutes)


def _expired(now: datetime):
    """무입력 시간이 지났고 처리 중이 아닌 세션."""
    return and_(
        ChatSession.last_active_at < now - _idle(),
        or_(ChatSession.busy_until.is_(None), ChatSession.busy_until < now),
    )


async def purge_expired(session: AsyncSession, library_id: int | None = None) -> int:
    """끝난 세션을 지운다. 메시지는 CASCADE로 함께 지워진다. 지운 세션 수를 돌려준다."""
    query = delete(ChatSession).where(_expired(clock.now()))
    if library_id is not None:
        query = query.where(ChatSession.library_id == library_id)
    result = await session.execute(query)
    await session.commit()
    return result.rowcount or 0


def _today_start(now: datetime) -> datetime:
    zone = ZoneInfo(get_settings().library_timezone)
    return datetime.combine(now.astimezone(zone).date(), time.min, tzinfo=zone)


async def _check_daily_limit(session: AsyncSession, library_id: int, profile_name: str) -> None:
    runs = await session.scalar(
        select(func.count()).where(
            AgentRun.library_id == library_id,
            AgentRun.profile == profile_name,
            AgentRun.started_at >= _today_start(clock.now()),
        )
    )
    if (runs or 0) >= get_settings().librarian_daily_run_limit:
        raise LimitExceededError("오늘 AI 사서 이용 한도에 이르렀습니다. 내일 다시 이용해 주세요")


async def _active_session(
    session: AsyncSession, library_id: int, session_id: uuid.UUID
) -> ChatSession:
    chat = await session.scalar(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.library_id == library_id,
            ChatSession.last_active_at >= clock.now() - _idle(),
        )
    )
    if chat is None:
        raise NotFoundError("대화를 찾을 수 없습니다. 새 대화를 시작하세요")
    return chat


async def _turns(session: AsyncSession, library_id: int, session_id: uuid.UUID) -> int:
    return (
        await session.scalar(
            select(func.count()).where(
                ChatMessage.library_id == library_id,
                ChatMessage.session_id == session_id,
                ChatMessage.role == ChatRole.USER,
            )
        )
        or 0
    )


async def _claim(session: AsyncSession, library_id: int, session_id: uuid.UUID) -> None:
    """처리 중 표시를 원자적으로 잡는다. 입력이 들어왔으므로 만료 시간도 다시 시작한다."""
    now = clock.now()
    claimed = await session.scalar(
        update(ChatSession)
        .where(
            ChatSession.id == session_id,
            ChatSession.library_id == library_id,
            or_(ChatSession.busy_until.is_(None), ChatSession.busy_until < now),
        )
        .values(busy_until=now + BUSY_TIMEOUT, last_active_at=now)
        .returning(ChatSession.id)
    )
    if claimed is None:
        await session.rollback()
        raise ConflictError("이전 질문에 답하는 중입니다. 답이 나온 뒤에 다시 보내 주세요")


async def _history(session: AsyncSession, library_id: int, session_id: uuid.UUID) -> History:
    """이전 대화. 책 표시는 이용자 문장 앞의 안내(`Instruction`)가 된다."""
    rows = await session.execute(
        select(ChatMessage.role, ChatMessage.content, ChatMessage.note)
        .where(ChatMessage.library_id == library_id, ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id)
    )
    messages: list[UserMessage | AssistantMessage | Instruction] = []
    for role, content, note in rows:
        if note:
            messages.append(Instruction(note))
        if role == ChatRole.ASSISTANT:
            messages.append(AssistantMessage(content))
        elif content:
            messages.append(UserMessage(content))
    return tuple(messages)


def _books_note(template: str, books: Sequence[Candidate]) -> str:
    listed = ", ".join(f"#{c.library_book.id} {c.library_book.shown('title')}" for c in books)
    return template.format(books=listed)


async def prepare_turn(
    session: AsyncSession,
    library_id: int,
    session_id: uuid.UUID | None,
    text: str | None,
    *,
    profile_name: str,
    selected_id: int | None = None,
) -> PreparedTurn:
    """응답을 시작하기 전의 확인. 실패하면 LLM은 호출되지 않고 세션과 메시지도 만들지 않는다."""
    if text is None and selected_id is None:
        raise ValueError("문장이나 고른 책이 있어야 한다")
    await purge_expired(session, library_id)
    selected = await get_findable(session, library_id, selected_id) if selected_id else None
    if text is not None:
        await _check_daily_limit(session, library_id, profile_name)
    loan_mode = await session.scalar(select(Library.loan_mode).where(Library.id == library_id))
    assert loan_mode is not None
    if session_id is None:
        chat = ChatSession(id=uuid.uuid4(), library_id=library_id, last_active_at=clock.now())
        session.add(chat)
        await session.flush()
    else:
        chat = await _active_session(session, library_id, session_id)
        if await _turns(session, library_id, chat.id) >= get_settings().librarian_max_turns:
            raise ConflictError("이 대화의 질문 수 한도에 이르렀습니다. 새 대화를 시작하세요")
    await _claim(session, library_id, chat.id)
    history = await _history(session, library_id, chat.id)
    masked = await mask_personal(session, library_id, text) if text is not None else None
    if selected is not None:
        books, note = [selected], _books_note(SELECTED_NOTE, [selected])
    else:
        books = await found_in_text(session, library_id, masked or "")
        note = _books_note(FOUND_NOTE, books) if books else None
    found = tuple(await build_summaries(session, library_id, books))
    session.add(
        ChatMessage(
            library_id=library_id,
            session_id=chat.id,
            role=ChatRole.USER,
            content=masked or "",
            note=note,
        )
    )
    await session.commit()
    return PreparedTurn(library_id, chat.id, loan_mode, masked, history, note, found)


def _answer_text(message: str, cards: Sequence[BookCard]) -> str:
    """다음 턴의 "두 번째 책" 같은 질문을 위해 추천한 책의 id와 서명을 코드가 덧붙인다."""
    if not cards:
        return message
    books = ", ".join(f"#{c.library_book_id} {c.title}" for c in cards)
    return f"{message}\n{BOOKS_NOTE.format(books=books)}"


async def _release(session: AsyncSession, prepared: PreparedTurn) -> None:
    try:
        await session.rollback()
        await session.execute(
            update(ChatSession)
            .where(
                ChatSession.id == prepared.session_id,
                ChatSession.library_id == prepared.library_id,
            )
            .values(busy_until=None)
        )
        await session.commit()
    except Exception as exc:  # noqa: BLE001 - 표시는 시간이 지나면 풀린다
        logger.error("chat session release failed: %s", type(exc).__name__)


async def _finish(
    session: AsyncSession, prepared: PreparedTurn, answer: Any, done: DoneEvent
) -> list[ServerEvent]:
    shown = {book.library_book_id for book in prepared.found}
    # 찾은 책은 화면에 이미 있다. 답에 다시 넣었으면 카드와 노출 기록에서 뺀다(위반이 아니라 중복)
    cards = [
        c
        for c in await build_cards(session, prepared.library_id, answer)
        if c.library_book_id not in shown
    ]
    session.add(
        ChatMessage(
            library_id=prepared.library_id,
            session_id=prepared.session_id,
            role=ChatRole.ASSISTANT,
            content=_answer_text(answer.message, cards),
        )
    )
    add_events(session, prepared.library_id, done.run_id, cards)
    await session.commit()
    payload = AnswerPayload(
        message=answer.message,
        recommendations=cards,
        suggest_book_request=answer.suggest_book_request,
        loan_mode=prepared.loan_mode,
    )
    return [
        ServerEvent("answer", payload.model_dump(mode="json")),
        ServerEvent("done", {"run_id": done.run_id, "status": done.status.value}),
    ]


def _found_event(prepared: PreparedTurn) -> ServerEvent:
    return ServerEvent("found", {"books": [b.model_dump(mode="json") for b in prepared.found]})


async def stream_turn(
    session: AsyncSession, llm: LlmClient, profile: Profile, prepared: PreparedTurn
) -> AsyncIterator[ServerEvent]:
    """진행 사건은 바로 보내고, 답은 검사 뒤에 카드와 함께 보낸다. 끝나거나 끊기면 표시를 푼다."""
    if prepared.user_text is None:
        try:
            yield ServerEvent("session", {"session_id": str(prepared.session_id)})
            yield _found_event(prepared)
            yield ServerEvent("done", {"run_id": None, "status": SELECTED_STATUS})
        finally:
            with anyio.CancelScope(shield=True):
                await asyncio.shield(_release(session, prepared))
        return
    note = (Instruction(prepared.note),) if prepared.note else ()
    events = run(
        session=session,
        llm=llm,
        profile=profile,
        library_id=prepared.library_id,
        user_text=prepared.user_text,
        history=(*prepared.history, *note),
    )
    try:
        yield ServerEvent("session", {"session_id": str(prepared.session_id)})
        if prepared.found:
            yield _found_event(prepared)
        answer: Any = None
        async for event in events:
            if isinstance(event, StatusEvent):
                yield ServerEvent("status", {"text": event.text})
            elif isinstance(event, AnswerEvent):
                answer = event.answer
            elif isinstance(event, DoneEvent):
                for server_event in await _finish(session, prepared, answer, event):
                    yield server_event
    finally:

        async def cleanup() -> None:
            await events.aclose()
            await _release(session, prepared)

        with anyio.CancelScope(shield=True):
            await asyncio.shield(cleanup())


async def end_session(session: AsyncSession, library_id: int, session_id: uuid.UUID) -> None:
    """직접 초기화. 다른 기관의 세션은 없는 것과 같다."""
    result = await session.execute(
        delete(ChatSession).where(
            ChatSession.id == session_id, ChatSession.library_id == library_id
        )
    )
    if not result.rowcount:
        await session.rollback()
        raise NotFoundError("대화를 찾을 수 없습니다")
    await session.commit()


PURGE_INTERVAL_SECONDS = 60


async def purge_forever(
    open_session: Callable[[], AbstractAsyncContextManager[AsyncSession]],
    interval: float = PURGE_INTERVAL_SECONDS,
) -> None:
    """서버가 도는 동안 정해진 간격으로 모든 기관의 끝난 세션을 지운다. 실패하면 다음 회차다."""
    while True:
        try:
            async with open_session() as session:
                await purge_expired(session)
        except Exception as exc:  # noqa: BLE001 - 다음 회차에 다시 한다
            logger.error("chat session purge failed: %s", type(exc).__name__)
        await asyncio.sleep(interval)
