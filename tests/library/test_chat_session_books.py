"""[agent/chat-sessions] [agent/librarian] 대화 세션의 책: 책 id 칸과 최근 기록의 책(가짜 LLM)."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent import runner
from app.library import hooks
from app.library.models.chat import ChatMessage, ChatRole
from app.library.services.chat import session_books
from tests.conftest import Tenant
from tests.library.chat_helpers import LlmSlot, event, talk
from tests.library.librarian_helpers import add_held_book, search, submit
from tests.library.test_chat_lookup import picked
from tests.library.test_related_tool import related


async def _rows(session: AsyncSession, session_id: str) -> list[tuple[str, list[int]]]:
    rows = await session.execute(
        select(ChatMessage.role, ChatMessage.library_book_ids)
        .where(ChatMessage.session_id == uuid.UUID(session_id))
        .order_by(ChatMessage.id)
    )
    return [(str(role), list(ids)) for role, ids in rows]


async def _session_books(session: AsyncSession, library_id: int, session_id: str) -> list[int]:
    return list(await session_books(session, library_id, uuid.UUID(session_id)))


async def test_answer_row_book_ids(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/chat-sessions] 저장 내용 / 답 행의 책 id"""
    demian = await add_held_book(session, library_a.id, title="데미안")
    a = await add_held_book(session, library_a.id, title="싯다르타")
    b = await add_held_book(session, library_a.id, title="수레바퀴 아래서")
    fake_llm.script(search("헤세"), submit("세 권 있어요.", demian["id"], a["id"], b["id"]))
    events = await talk(kiosk_client, "데미안 있어요?")
    assert len(event(events, "answer")["recommendations"]) == 2
    rows = await _rows(session, event(events, "session")["session_id"])
    assert rows == [(ChatRole.USER, [demian["id"]]), (ChatRole.ASSISTANT, [a["id"], b["id"]])]


async def test_rows_without_books(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/chat-sessions] 저장 내용 / 책이 없는 행"""
    fake_llm.script(submit("찾는 책이 없어요.", suggest=True))
    events = await talk(kiosk_client, "공룡 책 있어요?")
    rows = await _rows(session, event(events, "session")["session_id"])
    assert rows == [(ChatRole.USER, []), (ChatRole.ASSISTANT, [])]


async def test_newest_first(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/librarian] 대화 세션의 책 / 최신 순(세 권은 service가 자른다)"""
    books = [await add_held_book(session, library_a.id, title=f"책{n}") for n in range(4)]
    session_id = event(await picked(kiosk_client, books[0]["id"]), "session")["session_id"]
    for book in books[1:]:
        await picked(kiosk_client, book["id"], session_id=session_id)
    found = await _session_books(session, library_a.id, session_id)
    assert found == [b["id"] for b in reversed(books)]


async def test_recommended_books_count(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/librarian] 대화 세션의 책 / 추천한 책"""
    rec = await add_held_book(session, library_a.id, title="싯다르타")
    fake_llm.script(search("헤세"), submit("있어요.", rec["id"]))
    session_id = event(await talk(kiosk_client, "헤세 책"), "session")["session_id"]
    assert await _session_books(session, library_a.id, session_id) == [rec["id"]]


async def test_same_book_once(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/librarian] 대화 세션의 책 / 같은 책 두 번"""
    a = await add_held_book(session, library_a.id, title="데미안")
    b = await add_held_book(session, library_a.id, title="싯다르타")
    session_id = event(await picked(kiosk_client, a["id"]), "session")["session_id"]
    await picked(kiosk_client, b["id"], session_id=session_id)
    await picked(kiosk_client, a["id"], session_id=session_id)
    assert await _session_books(session, library_a.id, session_id) == [a["id"], b["id"]]


async def test_other_sessions_are_not_read(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/librarian] 대화 세션의 책 / 다른 세션의 책"""
    a = await add_held_book(session, library_a.id, title="데미안")
    b = await add_held_book(session, library_a.id, title="싯다르타")
    first = event(await picked(kiosk_client, a["id"]), "session")["session_id"]
    second = event(await picked(kiosk_client, b["id"]), "session")["session_id"]
    assert await _session_books(session, library_a.id, second) == [b["id"]]
    assert await _session_books(session, library_a.id, first) == [a["id"]]


async def test_other_library_session_is_not_read(
    kiosk_client: AsyncClient,
    fake_llm: LlmSlot,
    session: AsyncSession,
    library_a: Tenant,
    library_b: Tenant,
) -> None:
    """[agent/librarian] 대화 세션의 책 / 다른 기관의 메시지를 읽지 않음"""
    a = await add_held_book(session, library_a.id, title="데미안")
    session_id = event(await picked(kiosk_client, a["id"]), "session")["session_id"]
    assert await _session_books(session, library_b.id, session_id) == []


async def test_this_turn_found_book_is_passed(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/librarian] 대화 세션의 책 / 이번 턴의 찾은 책(실행 값으로 넘김)"""
    demian = await add_held_book(session, library_a.id, title="데미안")
    seen: list = []
    original = runner._Execution.__init__

    def spy(self, *args, **kwargs):  # noqa: ANN001, ANN202
        original(self, *args, **kwargs)
        seen.append(dict(self.tool_values))

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(runner._Execution, "__init__", spy)
        fake_llm.script(submit("있어요.", suggest=False))
        await talk(kiosk_client, "데미안 있어요?")
    # 인코더는 테스트에서 끈다(`chat_helpers.fake_llm`). 실행 값 이름은 모두 `app/library`의 상수다
    assert seen == [{"session_book_ids": (demian["id"],), "query_encoder": None}]


async def test_latest_three_books(
    kiosk_client: AsyncClient,
    fake_llm: LlmSlot,
    session: AsyncSession,
    library_a: Tenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[agent/librarian] 대화 세션의 책 / 최신 순 3권"""
    books = [await add_held_book(session, library_a.id, title=f"책{n}") for n in range(4)]
    session_id = event(await picked(kiosk_client, books[0]["id"]), "session")["session_id"]
    for book in books[1:]:
        await picked(kiosk_client, book["id"], session_id=session_id)
    seen: list[list[int]] = []

    async def record(session, library_id, base_ids):  # noqa: ANN001, ANN202
        seen.append(list(base_ids))
        return None

    monkeypatch.setattr(hooks, "_related_scopes", [record])
    fake_llm.script(related(None), submit("찾아봤어요.", suggest=True))
    await talk(kiosk_client, "아무거나 더 있어요?", session_id)
    assert seen == [[books[3]["id"], books[2]["id"], books[1]["id"]]]
