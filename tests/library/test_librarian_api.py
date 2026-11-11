"""[agent/librarian] [agent/chat-sessions] [library/staff-auth] AI 사서 대화 API (가짜 LLM)."""

import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import AssistantMessage, UserMessage
from app.core import clock
from app.core.config import get_settings
from app.library.librarian import PROFILE_NAME
from app.library.models.chat import ChatMessage, ChatRole, ChatSession
from tests.conftest import Tenant
from tests.helpers import add_member, insert
from tests.library.chat_helpers import (
    LlmSlot,
    event,
    parse_sse,
    send,
    talk,
)
from tests.library.librarian_helpers import add_held_book, search, submit


async def _messages(session: AsyncSession, session_id: str) -> list[tuple[ChatRole, str]]:
    rows = await session.execute(
        select(ChatMessage.role, ChatMessage.content)
        .where(ChatMessage.session_id == uuid.UUID(session_id))
        .order_by(ChatMessage.id)
    )
    return [tuple(r) for r in rows]


async def _chat(session: AsyncSession, session_id: str) -> ChatSession | None:
    return await session.scalar(
        select(ChatSession)
        .where(ChatSession.id == uuid.UUID(session_id))
        .execution_options(populate_existing=True)
    )


async def _set(session: AsyncSession, session_id: str, **values) -> None:
    sets = ", ".join(f"{k} = :{k}" for k in values)
    await session.execute(
        text(f"UPDATE chat_sessions SET {sets} WHERE id = :id"),
        {"id": uuid.UUID(session_id), **values},
    )


async def _add_runs(session: AsyncSession, library_id: int, count: int) -> None:
    for _ in range(count):
        await insert(
            session,
            "agent_runs",
            library_id=library_id,
            profile=PROFILE_NAME,
            profile_version="v1",
            model="m",
            started_at=clock.now(),
        )


@pytest.fixture
async def dino(session: AsyncSession, library_a: Tenant):
    return await add_held_book(
        session, library_a.id, title="공룡 대백과", description="화석으로 보는 공룡 이야기"
    )


# --- 대화 요청 ---


async def test_event_order(kiosk_client: AsyncClient, fake_llm: LlmSlot, dino) -> None:
    """[agent/librarian] 대화 요청 / 사건 순서"""
    fake_llm.script(search("공룡"), submit("이 책을 보세요", dino["id"]))
    events = await talk(kiosk_client, "공룡 책 추천해줘")
    assert [e.name for e in events] == ["session", "status", "answer", "done"]
    assert uuid.UUID(event(events, "session")["session_id"])
    answer = event(events, "answer")
    assert answer["message"] == "이 책을 보세요"
    assert [c["title"] for c in answer["recommendations"]] == ["공룡 대백과"]
    assert answer["loan_mode"] == "internal"
    assert event(events, "done")["status"] == "completed"


async def test_no_token(client: AsyncClient, fake_llm: LlmSlot) -> None:
    """[agent/librarian] 대화 요청 / 토큰 없음"""
    res = await send(client, "공룡 책")
    assert res.status_code == 401
    assert fake_llm.calls == 0


async def test_library_id_in_body(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, library_b: Tenant
) -> None:
    """[agent/librarian] 대화 요청 / 요청의 기관 값 무시"""
    res = await kiosk_client.post(
        "/librarian/messages", json={"message": "공룡 책", "library_id": library_b.id}
    )
    assert res.status_code == 422
    assert fake_llm.calls == 0


async def test_kiosk_can_talk(kiosk_client: AsyncClient, fake_llm: LlmSlot) -> None:
    """[library/staff-auth] 역할별 접근 제한 / 키오스크의 AI 사서 대화"""
    fake_llm.script(submit("없어요", suggest=True))
    res = await send(kiosk_client, "공룡 책")
    assert res.status_code == 200


# --- 진행 사건의 내용 ---


async def test_status_has_only_labels(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant, dino
) -> None:
    """[agent/librarian] 진행 사건의 내용 / 위반한 답이 응답에 없음"""
    lost = await add_held_book(session, library_a.id, "lost", title="분실된 공룡")
    fake_llm.script(
        search("공룡"),
        submit("분실된 공룡도 강력 추천합니다", dino["id"], lost["id"]),
        submit("이 책을 보세요", dino["id"]),
    )
    res = await send(kiosk_client, "공룡 책 추천해줘")
    body = res.text
    assert "강력 추천" not in body
    assert "화석으로 보는" not in body  # tool 결과(소개)
    assert '"keywords"' not in body  # tool 입력
    events = parse_sse(body)
    assert [e.data["text"] for e in events if e.name == "status"] == ["소장 도서를 찾고 있어요"]


# --- 운영 방식별 안내 ---


async def test_imported_answer(
    kiosk_client_b: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_b: Tenant
) -> None:
    """[agent/librarian] 운영 방식별 안내 / 가져오기 기관의 카드"""
    synced = clock.now() - timedelta(days=1)
    book = await add_held_book(
        session, library_b.id, title="공룡 백과", holding={"last_synced_at": synced}
    )
    fake_llm.script(submit("이 책요", book["id"]))
    answer = event(await talk(kiosk_client_b, "공룡 책"), "answer")
    assert answer["loan_mode"] == "imported"
    assert answer["recommendations"][0]["status_synced_at"] is not None


# --- 대화 이어 가기 ---


async def test_second_turn(kiosk_client: AsyncClient, fake_llm: LlmSlot, dino) -> None:
    """[agent/chat-sessions] 대화 이어 가기 / 두 번째 턴, 추천한 책 전달"""
    fake_llm.script(submit("이 책을 보세요", dino["id"]))
    first = await talk(kiosk_client, "공룡 책 추천해줘")
    session_id = event(first, "session")["session_id"]
    llm = fake_llm.script(submit("그 책은 화석 이야기예요"))
    second = await talk(kiosk_client, "그 책은 어떤 내용이에요?", session_id)
    assert event(second, "session")["session_id"] == session_id
    messages = llm.requests[0]["messages"]
    assert messages[0] == UserMessage("공룡 책 추천해줘")
    assert isinstance(messages[1], AssistantMessage)
    assert messages[1].text.startswith("이 책을 보세요")
    assert f"#{dino['id']} 공룡 대백과" in messages[1].text
    assert messages[2] == UserMessage("그 책은 어떤 내용이에요?")
    assert len(messages) == 3


# --- 세션의 기관 범위, 만료, 초기화 ---


async def test_other_library_session(
    kiosk_client: AsyncClient,
    kiosk_client_b: AsyncClient,
    fake_llm: LlmSlot,
    session: AsyncSession,
) -> None:
    """[agent/chat-sessions] 세션의 기관 범위 / 다른 기관의 세션"""
    fake_llm.script(submit("없어요", suggest=True))
    session_id = event(await talk(kiosk_client, "공룡 책"), "session")["session_id"]
    before = await _messages(session, session_id)
    res = await send(kiosk_client_b, "다른 건요?", session_id)
    assert res.status_code == 404
    assert await _messages(session, session_id) == before


async def test_expired_session(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession
) -> None:
    """[agent/chat-sessions] 세션 만료 / 시간이 지난 세션"""
    fake_llm.script(submit("없어요", suggest=True))
    session_id = event(await talk(kiosk_client, "공룡 책"), "session")["session_id"]
    await _set(session, session_id, last_active_at=clock.now() - timedelta(minutes=6))
    res = await send(kiosk_client, "다른 건요?", session_id)
    assert res.status_code == 404
    assert fake_llm.calls == 1
    assert await _chat(session, session_id) is None  # 요청 처리 때 먼저 지운다


async def test_input_extends_session(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession
) -> None:
    """[agent/chat-sessions] 세션 만료 / 입력하면 연장"""
    fake_llm.script(submit("없어요", suggest=True))
    session_id = event(await talk(kiosk_client, "공룡 책"), "session")["session_id"]
    await _set(session, session_id, last_active_at=clock.now() - timedelta(minutes=4))
    fake_llm.script(submit("없어요", suggest=True))
    before = clock.now()
    await talk(kiosk_client, "다른 건요?", session_id)
    chat = await _chat(session, session_id)
    assert chat is not None and chat.last_active_at >= before - timedelta(seconds=1)


async def test_delete_session(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession
) -> None:
    """[agent/chat-sessions] 직접 초기화 / 새 대화"""
    fake_llm.script(submit("없어요", suggest=True))
    session_id = event(await talk(kiosk_client, "공룡 책"), "session")["session_id"]
    res = await kiosk_client.delete(f"/librarian/sessions/{session_id}")
    assert res.status_code == 204
    assert await _messages(session, session_id) == []
    assert (await send(kiosk_client, "다른 건요?", session_id)).status_code == 404


async def test_delete_other_library_session(
    kiosk_client: AsyncClient,
    kiosk_client_b: AsyncClient,
    fake_llm: LlmSlot,
    session: AsyncSession,
) -> None:
    """[agent/chat-sessions] 직접 초기화 / 다른 기관 세션 삭제"""
    fake_llm.script(submit("없어요", suggest=True))
    session_id = event(await talk(kiosk_client, "공룡 책"), "session")["session_id"]
    res = await kiosk_client_b.delete(f"/librarian/sessions/{session_id}")
    assert res.status_code == 404
    assert await _chat(session, session_id) is not None
    assert len(await _messages(session, session_id)) == 2


# --- 저장 내용, 개인정보 ---


async def test_stored_messages(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, dino
) -> None:
    """[agent/chat-sessions] 저장 내용 / 메시지 행"""
    fake_llm.script(search("공룡"), submit("이 책을 보세요", dino["id"]))
    session_id = event(await talk(kiosk_client, "공룡 책 추천해줘"), "session")["session_id"]
    rows = await _messages(session, session_id)
    assert [role for role, _ in rows] == [ChatRole.USER, ChatRole.ASSISTANT]
    assert rows[0][1] == "공룡 책 추천해줘"
    assert rows[1][1] == f"이 책을 보세요\n[추천한 책: #{dino['id']} 공룡 대백과]"
    assert "화석" not in str(rows)


async def test_personal_info_masked(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/chat-sessions] 개인정보 가리기 / 전화번호, 이메일과 주민등록번호, 회원번호

    LLM이 받은 문장과 저장된 문장을 함께 본다.
    """
    await add_member(session, library_a.id, "A-0042")
    values = ["010-1234-5678", "kim@example.com", "900101-1234567", "A-0042"]
    llm = fake_llm.script(submit("없어요", suggest=True))
    message = "연락처 010-1234-5678, kim@example.com, 900101-1234567, 번호 A-0042 공룡 책"
    session_id = event(await talk(kiosk_client, message), "session")["session_id"]
    sent = llm.requests[0]["messages"][-1].text
    stored = (await _messages(session, session_id))[0][1]
    for value in values:
        assert value not in sent and value not in stored
    assert "공룡 책" in sent


# --- 상한 ---


async def test_message_too_long(kiosk_client: AsyncClient, fake_llm: LlmSlot) -> None:
    """[agent/chat-sessions] 입력 상한 / 긴 문장"""
    assert (await send(kiosk_client, "가" * 501)).status_code == 422
    assert (await send(kiosk_client, "")).status_code == 422
    assert fake_llm.calls == 0


async def test_turn_limit(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[agent/chat-sessions] 턴 상한 / 턴 초과"""
    monkeypatch.setattr(get_settings(), "librarian_max_turns", 2)
    session_id = None
    for _ in range(2):
        fake_llm.script(submit("없어요", suggest=True))
        session_id = event(await talk(kiosk_client, "공룡 책", session_id), "session")["session_id"]
    llm = fake_llm.script(submit("없어요", suggest=True))
    res = await send(kiosk_client, "또요", session_id)
    assert res.status_code == 409
    assert llm.requests == []


async def test_daily_limit(
    kiosk_client: AsyncClient,
    fake_llm: LlmSlot,
    session: AsyncSession,
    library_a: Tenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[agent/chat-sessions] 일일 실행 상한 / 상한 도달"""
    monkeypatch.setattr(get_settings(), "librarian_daily_run_limit", 3)
    await _add_runs(session, library_a.id, 3)
    res = await send(kiosk_client, "공룡 책")
    assert res.status_code == 429
    assert fake_llm.calls == 0


async def test_daily_limit_other_library(
    kiosk_client: AsyncClient,
    fake_llm: LlmSlot,
    session: AsyncSession,
    library_b: Tenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[agent/chat-sessions] 일일 실행 상한 / 다른 기관의 실행 수"""
    monkeypatch.setattr(get_settings(), "librarian_daily_run_limit", 3)
    await _add_runs(session, library_b.id, 3)
    fake_llm.script(submit("없어요", suggest=True))
    assert (await send(kiosk_client, "공룡 책")).status_code == 200


async def test_daily_limit_counts_today_only(
    kiosk_client: AsyncClient,
    fake_llm: LlmSlot,
    session: AsyncSession,
    library_a: Tenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[agent/chat-sessions] 일일 실행 상한 / 기관 시간대의 오늘만 센다"""
    monkeypatch.setattr(get_settings(), "librarian_daily_run_limit", 1)
    await insert(
        session,
        "agent_runs",
        library_id=library_a.id,
        profile=PROFILE_NAME,
        profile_version="v1",
        model="m",
        started_at=clock.now() - timedelta(days=1, hours=1),
    )
    fake_llm.script(submit("없어요", suggest=True))
    assert (await send(kiosk_client, "공룡 책")).status_code == 200


# --- 동시 요청 금지 ---


async def test_busy_session(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession
) -> None:
    """[agent/chat-sessions] 동시 요청 금지 / 진행 중 재요청"""
    fake_llm.script(submit("없어요", suggest=True))
    session_id = event(await talk(kiosk_client, "공룡 책"), "session")["session_id"]
    await _set(session, session_id, busy_until=clock.now() + timedelta(minutes=1))
    llm = fake_llm.script(submit("없어요", suggest=True))
    assert (await send(kiosk_client, "다른 건요?", session_id)).status_code == 409
    assert llm.requests == []


async def test_stale_busy_marker(
    kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession
) -> None:
    """[agent/chat-sessions] 동시 요청 금지 / 오래된 진행 표시"""
    fake_llm.script(submit("없어요", suggest=True))
    session_id = event(await talk(kiosk_client, "공룡 책"), "session")["session_id"]
    await _set(session, session_id, busy_until=clock.now() - timedelta(seconds=1))
    fake_llm.script(submit("없어요", suggest=True))
    assert (await send(kiosk_client, "다른 건요?", session_id)).status_code == 200
    chat = await _chat(session, session_id)
    assert chat is not None and chat.busy_until is None
