"""[agent/librarian] 회원번호는 LLM과 대화·실행 기록에 남지 않음(카나리아).

화면의 대출·반납·희망도서 입력칸은 REST로 바로 가고, AI 사서에는 쓰기 tool이 없다. 같은
키오스크에서 카나리아 회원번호로 대출·반납·신청을 한 뒤 대화하고, 가짜 LLM이 받은 요청과 기록에
그 번호가 없는지 본다.
"""

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Tenant
from tests.helpers import add_holding, add_member
from tests.library.chat_helpers import LlmSlot, event, talk
from tests.library.librarian_helpers import add_held_book, search, submit

CANARY = "ZQ-CANARY-7731"
RECORD_TABLES = (
    "agent_runs",
    "agent_steps",
    "chat_messages",
    "chat_sessions",
    "recommendation_events",
)


async def test_member_number_canary_never_reaches_llm_or_records(
    kiosk_client: AsyncClient,
    admin_client: AsyncClient,
    fake_llm: LlmSlot,
    session: AsyncSession,
    library_a: Tenant,
) -> None:
    """[agent/librarian] 쓰기 tool 없음 / 대화 후 데이터 변화 없음 (카나리아 회원번호)

    [agent/chat-sessions] 개인정보 가리기 / 전화번호, 이메일과 주민등록번호, 회원번호 (문장에 적은
    회원번호도 가린다)
    """
    await add_member(session, library_a.id, CANARY)
    book = await add_held_book(session, library_a.id, title="공룡 백과")
    await add_holding(session, library_a.id, book["id"], "EM-CAN-1")

    # 화면 입력칸이 부르는 REST: 대출, 반납, 희망도서 신청
    borrowed = await kiosk_client.post(
        "/loans", json={"accession_number": "EM-CAN-1", "member_number": CANARY}
    )
    assert borrowed.status_code == 201
    returned = await kiosk_client.post("/loans/return", json={"accession_number": "EM-CAN-1"})
    assert returned.status_code == 200
    requested = await kiosk_client.post(
        "/book-requests", json={"member_number": CANARY, "title": "작별하지 않는다"}
    )
    assert requested.status_code == 201
    assert CANARY not in requested.text

    # 같은 키오스크의 대화 두 턴. 두 번째 턴은 이용자가 회원번호를 문장에 적는다.
    fake_llm.script(search("공룡"), submit("공룡 책이에요", book["id"]))
    first = await talk(kiosk_client, "공룡 책 있어요?")
    session_id = event(first, "session")["session_id"]
    requests = list(fake_llm.llm.requests)  # script()는 턴마다 새 가짜 LLM을 만든다
    assert len(requests) == 2
    fake_llm.script(submit("화면 위 [대출·반납]에서 빌릴 수 있어요"))
    second = await talk(kiosk_client, f"회원번호 {CANARY}로 공룡 백과 빌려 줘", session_id)
    assert event(second, "answer")["message"]
    assert fake_llm.calls == 1
    requests += fake_llm.llm.requests

    sent = repr(requests)
    assert "[개인정보]" in sent  # 문장의 회원번호는 가려서 갔다
    dumped = []
    for table in RECORD_TABLES:
        rows = await session.execute(text(f"SELECT row_to_json(t)::text FROM {table} t"))
        dumped.extend(r[0] for r in rows)
    stored = " ".join(dumped)
    assert "공룡" in stored  # 기록은 남았다(검사가 헛돌지 않는지)
    assert CANARY not in sent
    assert CANARY not in stored

    # 같은 값이 관리자 희망도서 목록에는 나온다(카나리아가 실제로 쓰였는지 확인).
    listed = await admin_client.get("/book-requests")
    assert CANARY in listed.text
