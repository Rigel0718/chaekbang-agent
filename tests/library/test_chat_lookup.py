"""[agent/librarian] [agent/chat-sessions] 대화와 검색 잇기: 고른 책, 찾은 책 카드 (가짜 LLM)."""

from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import Instruction, UserMessage
from app.core.config import get_settings
from app.features.children.rules import is_children_request
from app.library.models.chat import ChatMessage, ChatSession
from tests.conftest import Tenant
from tests.library.chat_helpers import LlmSlot, Sse, event, parse_sse, talk
from tests.library.librarian_helpers import add_held_book, search, submit
from tests.library.test_librarian_api import _add_runs


async def pick(
    client: AsyncClient, book_id: int, message: str | None = None, session_id: str | None = None
) -> Response:
    body: dict[str, Any] = {"selected_library_book_id": book_id}
    if message is not None:
        body["message"] = message
    if session_id is not None:
        body["session_id"] = session_id
    return await client.post("/librarian/messages", json=body)


async def picked(client: AsyncClient, book_id: int, **kw: Any) -> list[Sse]:
    res = await pick(client, book_id, **kw)
    assert res.status_code == 200, res.text
    return parse_sse(res.text)


def _names(events: list[Sse]) -> list[str]:
    return [e.name for e in events]


async def _count(session: AsyncSession, table: str) -> int:
    return await session.scalar(text(f"select count(*) from {table}"))


@pytest.fixture
async def demian(session: AsyncSession, library_a: Tenant):
    return await add_held_book(session, library_a.id, title="데미안", author="헤르만 헤세")


# --- 대화 요청 ---


async def test_selected_only(kiosk_client: AsyncClient, fake_llm: LlmSlot, demian) -> None:
    """[agent/librarian] 대화 요청 / 고른 책만"""
    events = await picked(kiosk_client, demian["id"])
    assert _names(events) == ["session", "found", "done"]
    [book] = event(events, "found")["books"]
    assert (book["library_book_id"], book["title"]) == (demian["id"], "데미안")
    assert "reason" not in book
    assert fake_llm.calls == 0


async def test_selected_only_done(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, demian
) -> None:
    """[agent/librarian] 대화 요청 / 고른 책만 보낸 턴의 끝"""
    events = await picked(kiosk_client, demian["id"])
    assert event(events, "done") == {"run_id": None, "status": "selected"}
    assert await _count(session, "agent_runs") == 0


async def test_selected_with_message(kiosk_client: AsyncClient, fake_llm: LlmSlot, demian) -> None:
    """[agent/librarian] 대화 요청 / 고른 책과 문장"""
    llm = fake_llm.script(search("가벼운"), submit("찾아볼게요", suggest=True))
    events = await picked(kiosk_client, demian["id"], message="이거 말고 좀 가벼운 거")
    names = _names(events)
    assert names.index("found") < names.index("status")
    messages = llm.requests[0]["messages"]
    note = f"[고른 책: #{demian['id']} 데미안]"
    assert Instruction(note) in messages
    users = [m.text for m in messages if isinstance(m, UserMessage)]
    assert users == ["이거 말고 좀 가벼운 거"]


async def test_message_and_selected_missing(kiosk_client: AsyncClient) -> None:
    """[agent/librarian] 대화 요청 / 문장과 고른 책 모두 없음"""
    res = await kiosk_client.post("/librarian/messages", json={})
    assert res.status_code == 422


async def test_selected_from_other_library(
    kiosk_client: AsyncClient,
    fake_llm: LlmSlot,
    session: AsyncSession,
    library_b: Tenant,
) -> None:
    """[agent/librarian] 대화 요청 / 다른 기관의 고른 책"""
    theirs = await add_held_book(session, library_b.id, title="데미안")
    before = (await _count(session, "chat_sessions"), await _count(session, "chat_messages"))
    res = await pick(kiosk_client, theirs["id"])
    assert res.status_code == 404
    assert (await _count(session, "chat_sessions"), await _count(session, "chat_messages")) == (
        before
    )
    assert fake_llm.calls == 0


async def test_lost_only_book_cannot_be_selected(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant
) -> None:
    lost = await add_held_book(session, library_a.id, "lost", title="잃어버린 책")
    assert (await pick(kiosk_client, lost["id"])).status_code == 404


# --- 저장 내용 ---


async def test_selected_only_row(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, demian
) -> None:
    """[agent/chat-sessions] 저장 내용 / 고른 책만 보낸 턴"""
    events = await picked(kiosk_client, demian["id"])
    session_id = event(events, "session")["session_id"]
    rows = (
        await session.execute(
            select(ChatMessage.role, ChatMessage.content, ChatMessage.note).where(
                ChatMessage.session_id == session_id
            )
        )
    ).all()
    assert [tuple(r) for r in rows] == [("user", "", f"[고른 책: #{demian['id']} 데미안]")]


async def test_next_turn_context(kiosk_client: AsyncClient, fake_llm: LlmSlot, demian) -> None:
    """[agent/chat-sessions] 저장 내용 / 다음 턴의 문맥"""
    session_id = event(await picked(kiosk_client, demian["id"]), "session")["session_id"]
    llm = fake_llm.script(submit("찾아볼게요", suggest=True))
    await talk(kiosk_client, "비슷한 거 있어요?", session_id)
    messages = llm.requests[0]["messages"]
    assert Instruction(f"[고른 책: #{demian['id']} 데미안]") in messages
    assert [m.text for m in messages if isinstance(m, UserMessage)] == ["비슷한 거 있어요?"]


# --- 고른 책 턴의 상한 ---


async def test_selected_turn_counts_toward_turn_limit(
    kiosk_client: AsyncClient,
    fake_llm: LlmSlot,
    demian,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[agent/chat-sessions] 고른 책 턴의 상한 / 턴 상한"""
    monkeypatch.setattr(get_settings(), "librarian_max_turns", 2)
    fake_llm.script(submit("없어요", suggest=True))
    session_id = event(await talk(kiosk_client, "공룡 책"), "session")["session_id"]
    await picked(kiosk_client, demian["id"], session_id=session_id)
    llm = fake_llm.script(submit("없어요", suggest=True))
    res = await kiosk_client.post(
        "/librarian/messages", json={"message": "또요", "session_id": session_id}
    )
    assert res.status_code == 409
    assert llm.requests == []


async def test_selected_turn_ignores_daily_limit(
    kiosk_client: AsyncClient,
    fake_llm: LlmSlot,
    session: AsyncSession,
    library_a: Tenant,
    demian,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[agent/chat-sessions] 고른 책 턴의 상한 / 일일 실행 상한"""
    monkeypatch.setattr(get_settings(), "librarian_daily_run_limit", 1)
    await _add_runs(session, library_a.id, 1)
    events = await picked(kiosk_client, demian["id"])
    assert "found" in _names(events)
    sessions = await session.scalar(select(func.count()).select_from(ChatSession))
    assert sessions == 1


# --- 찾은 책 카드 ---


async def test_found_title_in_message(kiosk_client: AsyncClient, fake_llm: LlmSlot, demian) -> None:
    """[agent/librarian] 찾은 책 카드 / 서명을 말한 문장"""
    llm = fake_llm.script(submit("네, 있어요."))
    events = await talk(kiosk_client, "데미안 있어요?")
    assert _names(events)[:2] == ["session", "found"]  # LLM 답과 진행 문구보다 먼저
    assert [b["library_book_id"] for b in event(events, "found")["books"]] == [demian["id"]]
    assert Instruction(f"[찾은 책: #{demian['id']} 데미안]") in llm.requests[0]["messages"]


async def test_found_title_with_typo(kiosk_client: AsyncClient, fake_llm: LlmSlot, demian) -> None:
    """[agent/librarian] 찾은 책 카드 / 오타가 있는 문장"""
    fake_llm.script(submit("네, 있어요."))
    events = await talk(kiosk_client, "데미얀 있나요")
    assert [b["library_book_id"] for b in event(events, "found")["books"]] == [demian["id"]]


async def test_found_title_with_edition_marker(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/librarian] 찾은 책 카드 / 판본 표기가 붙은 서명을 말한 문장"""
    book = await add_held_book(session, library_a.id, title="[예스리커버] 아는 만큼 보인다")
    fake_llm.script(submit("네, 있어요."))
    events = await talk(kiosk_client, "아는 만큼 보인다 있어요?")
    assert [b["library_book_id"] for b in event(events, "found")["books"]] == [book["id"]]


async def test_no_found_for_topic_request(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/librarian] 찾은 책 카드 / 주제 요청"""
    await add_held_book(session, library_a.id, title="진짜 재밌는 공룡 그림책")
    fake_llm.script(submit("찾아볼게요", suggest=True))
    events = await talk(kiosk_client, "공룡 책 추천해줘")
    assert "found" not in _names(events)


async def test_found_not_recorded(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, demian
) -> None:
    """[agent/librarian] 찾은 책 카드 / 노출 기록 없음"""
    fake_llm.script(submit("네, 2층에 있어요."))
    events = await talk(kiosk_client, "데미안 있어요?")
    assert event(events, "found")["books"]
    assert event(events, "answer")["recommendations"] == []
    assert await _count(session, "recommendation_events") == 0


async def test_title_words_do_not_make_children_request(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/librarian] 찾은 책 카드 / 서명 속 어린이 낱말"""
    kids = await add_held_book(session, library_a.id, title="법 만드는 아이들")
    session_id = event(await picked(kiosk_client, kids["id"]), "session")["session_id"]
    llm = fake_llm.script(submit("찾아볼게요", suggest=True))
    await talk(kiosk_client, "비슷한 거 있어요?", session_id)
    users = [m.text for m in llm.requests[0]["messages"] if isinstance(m, UserMessage)]
    assert not is_children_request(users)


async def test_found_book_not_repeated_in_answer(
    kiosk_client: AsyncClient,
    fake_llm: LlmSlot,
    session: AsyncSession,
    library_a: Tenant,
    demian,
) -> None:
    """[agent/librarian] 찾은 책 카드 / 찾은 책을 다시 추천"""
    other = await add_held_book(session, library_a.id, title="싯다르타")
    fake_llm.script(submit("둘 다 있어요.", demian["id"], other["id"]))
    events = await talk(kiosk_client, "데미안 있어요?")
    cards = event(events, "answer")["recommendations"]
    assert [c["library_book_id"] for c in cards] == [other["id"]]
    shown = await session.scalars(text("select library_book_id from recommendation_events"))
    assert list(shown) == [other["id"]]


async def test_found_general_book_in_children_request(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/librarian] 찾은 책 카드 / 어린이 요청에서 찾은 일반 도서"""
    adult = await add_held_book(session, library_a.id, title="데미안")
    other_adult = await add_held_book(session, library_a.id, title="싯다르타")
    llm = fake_llm.script(
        submit("이 책도 있어요.", other_adult["id"]),
        submit("어린이 책은 없어요.", suggest=True),
    )
    events = await talk(kiosk_client, "7살 아이가 데미안 읽어도 되나요?")
    assert [b["library_book_id"] for b in event(events, "found")["books"]] == [adult["id"]]
    assert event(events, "answer")["recommendations"] == []
    assert len(llm.requests) == 2  # 일반 도서 추천은 어린이 검사에 막혀 다시 물었다
