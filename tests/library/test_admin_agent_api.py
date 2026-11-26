"""[agent/admin], [agent/chat-sessions] 운영 에이전트 대화 API: 권한, 사건, 기록, 세션 종류."""

import uuid
from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient, Response
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.models import AgentRun, AgentStep
from app.core import clock
from app.core.config import get_settings
from app.library import admin_agent
from app.library import librarian as librarian_profile
from app.library.models.chat import ChatMessage, ChatRole, ChatSession
from tests.agent.fakes import call, tool_turn
from tests.conftest import Tenant
from tests.helpers import add_held_book, add_member, insert
from tests.library.chat_helpers import LlmSlot, event, parse_sse
from tests.library.chat_helpers import talk as librarian_talk


def answer(message: str, unsupported: str | None = None):
    return tool_turn(
        call("submit_answer", {"message": message, "unsupported": unsupported}, "answer")
    )


def status_call() -> Any:
    return tool_turn(
        call("get_collection_status", {"group_by": None, "fields": None, "audience": None})
    )


async def send(client: AsyncClient, message: str, session_id: str | None = None) -> Response:
    body: dict[str, Any] = {"message": message}
    if session_id is not None:
        body["session_id"] = session_id
    return await client.post("/admin-agent/messages", json=body)


async def talk(client: AsyncClient, message: str, session_id: str | None = None):
    res = await send(client, message, session_id)
    assert res.status_code == 200, res.text
    return parse_sse(res.text)


async def _run(session: AsyncSession, run_id: int) -> AgentRun:
    row = await session.scalar(
        select(AgentRun).where(AgentRun.id == run_id).execution_options(populate_existing=True)
    )
    assert row is not None
    return row


async def _set(session: AsyncSession, session_id: str, **values) -> None:
    sets = ", ".join(f"{k} = :{k}" for k in values)
    await session.execute(
        text(f"UPDATE chat_sessions SET {sets} WHERE id = :id"),
        {"id": uuid.UUID(session_id), **values},
    )


async def test_event_order(admin_client: AsyncClient, fake_llm: LlmSlot) -> None:
    """[agent/admin] 운영 에이전트 대화 요청 / 사건 순서"""
    fake_llm.script(status_call(), answer("모두 0권이에요"))
    events = await talk(admin_client, "책이 모두 몇 권이야?")
    assert [e.name for e in events] == ["session", "status", "answer", "done"]
    assert event(events, "answer") == {"message": "모두 0권이에요", "unsupported": None}
    assert event(events, "done")["status"] == "completed"


def grouped_status_call() -> Any:
    return tool_turn(
        call("get_collection_status", {"group_by": "field", "fields": None, "audience": None})
    )


async def test_event_order_with_result(
    admin_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/admin] 운영 에이전트 대화 요청 / 결과 사건이 있는 순서"""
    await add_held_book(session, library_a.id, title="표에 나올 책", kdc="813")
    fake_llm.script(grouped_status_call(), answer("문학이 1권이에요"))
    events = await talk(admin_client, "분야별로 책이 몇 권씩 있어?")
    assert [e.name for e in events] == ["session", "status", "result", "answer", "done"]
    table = event(events, "result")
    assert (table["kind"], table["title"], table["bar_column"]) == ("table", "분야별 장서", 1)
    assert ["문학", 1, 1] in table["rows"]


async def test_result_not_in_chat_messages(
    admin_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/admin] 결과 사건의 개인정보와 기관 범위 / 대화 기록에 없음"""
    await add_held_book(session, library_a.id, title="기록에 없을 서명", kdc="813")
    fake_llm.script(grouped_status_call(), answer("분야별로 세었어요"))
    events = await talk(admin_client, "분야별로 책이 몇 권씩 있어?")
    assert "기록에 없을 서명" not in str(event(events, "result"))  # 묶음 표에는 서명이 없다
    session_id = uuid.UUID(event(events, "session")["session_id"])
    rows = await session.execute(
        select(ChatMessage.role, ChatMessage.content).where(ChatMessage.session_id == session_id)
    )
    assert [tuple(r) for r in rows] == [
        (ChatRole.USER, "분야별로 책이 몇 권씩 있어?"),
        (ChatRole.ASSISTANT, "분야별로 세었어요"),
    ]


async def test_events_by_name_still_have_answer(
    admin_client: AsyncClient, fake_llm: LlmSlot
) -> None:
    """[platform/admin-agent-evals] 평가 러너처럼 사건을 이름별로 모아도 답과 끝을 읽는다"""
    fake_llm.script(grouped_status_call(), answer("분야별로 세었어요"))
    events = {e.name: e.data for e in await talk(admin_client, "분야별로 책이 몇 권씩 있어?")}
    assert events["answer"]["message"] == "분야별로 세었어요"
    assert events["done"]["status"] == "completed"
    assert events["result"]["kind"] == "table"


async def test_kiosk_forbidden(kiosk_client: AsyncClient, fake_llm: LlmSlot) -> None:
    """[agent/admin] 운영 에이전트 대화 요청 / 키오스크 토큰"""
    res = await send(kiosk_client, "책이 모두 몇 권이야?")
    assert res.status_code == 403
    assert fake_llm.calls == 0


async def test_no_token(client: AsyncClient, fake_llm: LlmSlot) -> None:
    """[agent/admin] 운영 에이전트 대화 요청 / 토큰 없음"""
    assert (await send(client, "책이 모두 몇 권이야?")).status_code == 401


async def test_library_id_rejected(admin_client: AsyncClient, fake_llm: LlmSlot) -> None:
    """[agent/admin] 운영 에이전트 대화 요청 / 요청의 기관 값 무시"""
    res = await admin_client.post(
        "/admin-agent/messages", json={"message": "몇 권?", "library_id": 2}
    )
    assert res.status_code == 422
    assert fake_llm.calls == 0


async def test_end_session(admin_client: AsyncClient, fake_llm: LlmSlot) -> None:
    """[agent/admin] 운영 에이전트 세션 끝내기 / 세션 삭제"""
    fake_llm.script(answer("답"))
    session_id = event(await talk(admin_client, "몇 권?"), "session")["session_id"]
    assert (await admin_client.delete(f"/admin-agent/sessions/{session_id}")).status_code == 204
    assert (await send(admin_client, "다시", session_id)).status_code == 404


async def test_unsupported_recorded(
    admin_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession
) -> None:
    """[agent/admin] 운영 에이전트 최종 답 / 못 하는 분석의 기록"""
    fake_llm.script(answer("그 분석은 아직 못 해요", "topic_count"))
    question = "공룡 책 몇 권 있어? 고유질문표시"
    events = await talk(admin_client, question)
    row = await _run(session, event(events, "done")["run_id"])
    assert (row.profile, row.answer_record) == (
        admin_agent.PROFILE_NAME,
        {"unsupported": "topic_count"},
    )
    steps = await session.scalars(select(AgentStep).where(AgentStep.run_id == row.id))
    dumped = str([row.__dict__] + [s.__dict__ for s in steps])
    assert "고유질문표시" not in dumped


async def test_answered_records_null(
    admin_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession
) -> None:
    """[agent/admin] 운영 에이전트 최종 답 / 답한 분석"""
    fake_llm.script(status_call(), answer("모두 0권이에요"))
    events = await talk(admin_client, "책이 모두 몇 권이야?")
    row = await _run(session, event(events, "done")["run_id"])
    assert row.answer_record == {"unsupported": None}
    [step] = [
        s
        for s in await session.scalars(select(AgentStep).where(AgentStep.run_id == row.id))
        if s.name == "get_collection_status"
    ]
    assert step.detail == {"group_by": None, "fields": None, "audience": None}


async def test_messages_masked(
    admin_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/chat-sessions] 세션 종류 / 운영 에이전트 문장 가리기"""
    await add_member(session, library_a.id, "M77881234")
    llm = fake_llm.script(answer("그 분석은 아직 못 해요", "patron_info"))
    events = await talk(admin_client, "M77881234 회원이 빌린 책 알려줘")
    sent = str(llm.requests[0]["messages"])
    assert "M77881234" not in sent
    session_id = uuid.UUID(event(events, "session")["session_id"])
    rows = await session.execute(
        select(ChatMessage.role, ChatMessage.content).where(ChatMessage.session_id == session_id)
    )
    stored = [tuple(r) for r in rows]
    assert [role for role, _ in stored] == [ChatRole.USER, ChatRole.ASSISTANT]
    assert all("M77881234" not in content for _, content in stored)


async def test_librarian_session_not_usable(
    admin_client: AsyncClient, kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession
) -> None:
    """[agent/chat-sessions] 세션 종류 / AI 사서 세션을 운영 에이전트로"""
    from tests.library.librarian_helpers import submit

    fake_llm.script(submit("없어요", suggest=True))
    session_id = event(await librarian_talk(kiosk_client, "공룡 책"), "session")["session_id"]
    res = await send(admin_client, "몇 권?", session_id)
    assert res.status_code == 404
    count = await session.scalar(
        select(ChatMessage.id).where(ChatMessage.session_id == uuid.UUID(session_id)).limit(5)
    )
    assert count is not None
    assert fake_llm.calls == 1


async def test_admin_session_not_usable_by_librarian(
    admin_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession
) -> None:
    """[agent/chat-sessions] 세션 종류 / 운영 에이전트 세션을 AI 사서로"""
    fake_llm.script(answer("답"))
    session_id = event(await talk(admin_client, "몇 권?"), "session")["session_id"]
    res = await admin_client.post(
        "/librarian/messages", json={"message": "공룡 책", "session_id": session_id}
    )
    assert res.status_code == 404
    assert (await admin_client.delete(f"/librarian/sessions/{session_id}")).status_code == 404
    assert await session.get(ChatSession, uuid.UUID(session_id)) is not None


async def test_other_library_admin_session(
    admin_client: AsyncClient, admin_client_b: AsyncClient, fake_llm: LlmSlot
) -> None:
    """[agent/chat-sessions] 세션 종류 / 운영 에이전트 세션의 기관 범위"""
    fake_llm.script(answer("답"))
    session_id = event(await talk(admin_client, "몇 권?"), "session")["session_id"]
    assert (await send(admin_client_b, "다시", session_id)).status_code == 404
    assert (await admin_client_b.delete(f"/admin-agent/sessions/{session_id}")).status_code == 404


async def test_expiry_by_kind(
    admin_client: AsyncClient, kiosk_client: AsyncClient, fake_llm: LlmSlot, session: AsyncSession
) -> None:
    """[agent/chat-sessions] 세션 만료 / 종류별 만료 시간"""
    from tests.library.chat_helpers import send as librarian_send
    from tests.library.librarian_helpers import submit

    fake_llm.script(submit("없어요", suggest=True), answer("답"), answer("다시 답"))
    kiosk_id = event(await librarian_talk(kiosk_client, "공룡 책"), "session")["session_id"]
    admin_id = event(await talk(admin_client, "몇 권?"), "session")["session_id"]
    ten_minutes_ago = clock.now() - timedelta(minutes=10)
    await _set(session, kiosk_id, last_active_at=ten_minutes_ago)
    await _set(session, admin_id, last_active_at=ten_minutes_ago)
    assert (await librarian_send(kiosk_client, "다른 건요?", kiosk_id)).status_code == 404
    assert (await send(admin_client, "다시", admin_id)).status_code == 200


async def test_daily_limit_by_kind(
    admin_client: AsyncClient,
    fake_llm: LlmSlot,
    session: AsyncSession,
    library_a: Tenant,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[agent/chat-sessions] 일일 실행 상한 / 다른 종류의 실행 수"""
    monkeypatch.setattr(get_settings(), "librarian_daily_run_limit", 2)
    monkeypatch.setattr(get_settings(), "admin_daily_run_limit", 2)
    for _ in range(2):
        await insert(
            session,
            "agent_runs",
            library_id=library_a.id,
            profile=librarian_profile.PROFILE_NAME,
            profile_version="v1",
            model="m",
            started_at=clock.now(),
        )
    fake_llm.script(answer("답"))
    assert (await send(admin_client, "몇 권?")).status_code == 200
    await insert(
        session,
        "agent_runs",
        library_id=library_a.id,
        profile=admin_agent.PROFILE_NAME,
        profile_version="v1",
        model="m",
        started_at=clock.now(),
    )
    assert (await send(admin_client, "몇 권?")).status_code == 429
