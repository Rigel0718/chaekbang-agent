"""[agent/chat-sessions] 대화 세션의 중단, 끝난 세션의 삭제. service를 직접 부른다."""

import asyncio
import contextlib
import uuid
from datetime import timedelta

import anyio
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import LlmTurn
from app.agent.models import AgentRun, RunStatus
from app.core import clock
from app.library.librarian import PROFILE_NAME
from app.library.models.chat import ChatMessage, ChatSession, RecommendationEvent
from app.library.services import chat
from tests.agent.fakes import FakeLlm
from tests.conftest import Tenant
from tests.library.librarian_helpers import add_held_book, librarian, search, submit


async def _prepare(session: AsyncSession, library_id: int, session_id=None, text="공룡 책"):
    return await chat.prepare_turn(session, library_id, session_id, text, profile_name=PROFILE_NAME)


async def _turn(session: AsyncSession, library_id: int, llm, session_id=None) -> list:
    prepared = await _prepare(session, library_id, session_id)
    return [e async for e in chat.stream_turn(session, llm, librarian(), prepared)]


async def _busy(session: AsyncSession, session_id: uuid.UUID):
    return await session.scalar(
        select(ChatSession.busy_until)
        .where(ChatSession.id == session_id)
        .execution_options(populate_existing=True)
    )


class SlowLlm(FakeLlm):
    """첫 호출 뒤 두 번째 호출에서 멈춘다. 응답 중단을 흉내 낸다."""

    async def complete(self, **kwargs) -> LlmTurn:
        if self.requests:
            self.requests.append(kwargs)
            await asyncio.sleep(3600)
        return await super().complete(**kwargs)


async def test_reuse_after_close(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/chat-sessions] 동시 요청 금지 / 중단 뒤 재사용 (받던 쪽이 멈춤)"""
    prepared = await _prepare(session, library_a.id)
    stream = chat.stream_turn(session, FakeLlm([search("공룡")]), librarian(), prepared)
    first = await anext(stream)
    assert first.name == "session"
    assert await _busy(session, prepared.session_id) is not None
    await stream.aclose()
    assert await _busy(session, prepared.session_id) is None
    events = await _turn(session, library_a.id, FakeLlm([submit("없어요")]), prepared.session_id)
    assert events[-1].name == "done"


async def test_reuse_after_cancel(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/chat-sessions] 동시 요청 금지 / 중단 뒤 재사용 (서버가 응답을 취소함)"""
    prepared = await _prepare(session, library_a.id)
    got_status = asyncio.Event()

    async def consume() -> None:
        stream = chat.stream_turn(session, SlowLlm([search("공룡")]), librarian(), prepared)
        async for item in stream:
            if item.name == "status":
                got_status.set()

    async with anyio.create_task_group() as group:
        group.start_soon(consume)
        await got_status.wait()
        await asyncio.sleep(0.05)  # 두 번째 LLM 호출에서 멈춘 상태
        group.cancel_scope.cancel()

    assert await _busy(session, prepared.session_id) is None
    status = await session.scalar(
        select(AgentRun.status)
        .where(AgentRun.library_id == library_a.id)
        .execution_options(populate_existing=True)
    )
    assert status == RunStatus.CANCELLED
    events = await _turn(session, library_a.id, FakeLlm([submit("없어요")]), prepared.session_id)
    assert events[-1].name == "done"


# --- 끝난 세션의 삭제 ---


async def _old_session(session: AsyncSession, library_id: int) -> uuid.UUID:
    events = await _turn(session, library_id, FakeLlm([submit("없어요", suggest=True)]))
    session_id = uuid.UUID(events[0].data["session_id"])
    await session.execute(
        text("UPDATE chat_sessions SET last_active_at = :t WHERE id = :id"),
        {"t": clock.now() - timedelta(minutes=10), "id": session_id},
    )
    return session_id


async def _count(session: AsyncSession, model, session_id: uuid.UUID) -> int:
    column = ChatSession.id if model is ChatSession else ChatMessage.session_id
    return await session.scalar(select(func.count()).where(column == session_id)) or 0


async def test_periodic_purge(session: AsyncSession, library_a: Tenant, library_b: Tenant) -> None:
    """[agent/chat-sessions] 끝난 세션의 삭제 / 주기 삭제"""
    old_a = await _old_session(session, library_a.id)
    old_b = await _old_session(session, library_b.id)

    purged = asyncio.Event()

    @contextlib.asynccontextmanager
    async def open_session():
        yield session
        purged.set()

    task = asyncio.create_task(chat.purge_forever(open_session, interval=3600))
    try:
        await asyncio.wait_for(purged.wait(), timeout=5)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    for session_id in (old_a, old_b):
        assert await _count(session, ChatSession, session_id) == 0
        assert await _count(session, ChatMessage, session_id) == 0


async def test_purge_keeps_active(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/chat-sessions] 끝난 세션의 삭제 / 진행 중 세션은 유지"""
    active = await _turn(session, library_a.id, FakeLlm([submit("없어요", suggest=True)]))
    active_id = uuid.UUID(active[0].data["session_id"])
    old = await _old_session(session, library_a.id)
    assert await chat.purge_expired(session) == 1
    assert await _count(session, ChatSession, old) == 0
    assert await _count(session, ChatSession, active_id) == 1
    assert await _count(session, ChatMessage, active_id) == 2


async def test_purge_keeps_busy(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/chat-sessions] 끝난 세션의 삭제 / 진행 중 세션은 유지 (처리 중 표시)"""
    old = await _old_session(session, library_a.id)
    await session.execute(
        text("UPDATE chat_sessions SET busy_until = :t WHERE id = :id"),
        {"t": clock.now() + timedelta(minutes=1), "id": old},
    )
    assert await chat.purge_expired(session) == 0
    assert await _count(session, ChatSession, old) == 1


async def test_purge_keeps_runs_and_events(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/chat-sessions] 끝난 세션의 삭제 / 실행 기록은 유지"""
    book = await add_held_book(session, library_a.id, title="공룡 대백과")
    events = await _turn(session, library_a.id, FakeLlm([submit("이 책요", book["id"])]))
    session_id = uuid.UUID(events[0].data["session_id"])
    run_id = events[-1].data["run_id"]
    await chat.end_session(session, library_a.id, session_id)
    assert await session.scalar(select(func.count()).where(AgentRun.id == run_id)) == 1
    rows = await session.scalar(select(func.count()).where(RecommendationEvent.run_id == run_id))
    assert rows == 1


def test_lifespan_starts_purge(monkeypatch) -> None:
    """[agent/chat-sessions] 끝난 세션의 삭제 / 서버가 주기 작업을 시작"""
    import app.main as main

    started: list[bool] = []

    async def fake_purge(open_session, interval: float = 60) -> None:
        started.append(True)
        await asyncio.sleep(3600)

    async def check() -> None:
        async with main.lifespan(main.app):
            await asyncio.sleep(0)
            assert started == [True]

    monkeypatch.setattr(main, "purge_forever", fake_purge)
    monkeypatch.setattr(main, "get_engine", lambda: _NoEngine())
    asyncio.run(check())


class _NoEngine:
    async def dispose(self) -> None:
        return None
