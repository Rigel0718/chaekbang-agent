"""[circulation/member-basket] 담은 책 보관: 담기·불러오기·빼기·비우기, 3시간, 10권, 기관 분리.

회원 세션은 휴대폰 번호 로그인으로 만든다. 3시간 경과는 담은 시각을 직접 당겨 만든다
(시계를 바꾸면 3분짜리 회원 세션이 먼저 끝난다).
"""

import asyncio
import contextlib
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import get_settings
from app.library.schemas.catalog import BookSummary
from app.library.services import basket as basket_service
from app.library.services import chat
from tests.conftest import Tenant, make_client
from tests.helpers import add_held_book, add_member, add_staff_session, login_member

PHONE = "01012345678"
PHONE_Y = "01022223333"
REQUIRED = "회원 로그인이 필요합니다"
HEADER = "X-Member-Token"


@pytest.fixture
async def member(session: AsyncSession, library_a: Tenant) -> dict:
    return await add_member(session, library_a.id, "M0001", name="김비밀", phone=PHONE)


@pytest.fixture
async def me(kiosk_client: AsyncClient, member: dict) -> AsyncClient:
    """회원 로그인을 마친 키오스크 클라이언트."""
    await login_member(kiosk_client, PHONE)
    return kiosk_client


async def _book(session: AsyncSession, library_id: int, *statuses: str, **values) -> dict:
    return await add_held_book(session, library_id, *(statuses or ("available",)), **values)


async def _ids(client: AsyncClient) -> list[int]:
    res = await client.get("/basket")
    assert res.status_code == 200, res.text
    return [b["library_book_id"] for b in res.json()["books"]]


async def _age(session: AsyncSession, **interval: float) -> None:
    """담은 시각을 지금보다 이만큼 이전으로 당긴다(모든 줄)."""
    moved = clock.now() - timedelta(**interval)
    await session.execute(text("UPDATE basket_items SET added_at = :moved"), {"moved": moved})


async def _rows(session: AsyncSession) -> int:
    return await session.scalar(text("SELECT count(*) FROM basket_items"))


# --- 담기와 불러오기 ---


async def test_add_and_list_in_order(
    me: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/member-basket] 담은 책 보관과 불러오기 / 담고 불러오기"""
    a = await _book(session, library_a.id, title="가 책", isbn=None)
    b = await _book(session, library_a.id, title="나 책", isbn=None)
    for book in (a, b):
        assert (await me.put(f"/basket/{book['id']}")).status_code == 204
    res = await me.get("/basket")
    books = res.json()["books"]
    assert [x["library_book_id"] for x in books] == [a["id"], b["id"]]
    assert set(books[0]) == set(BookSummary.model_fields) | {"added_at"}


async def test_add_again_keeps_time(
    me: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/member-basket] 담은 책 보관과 불러오기 / 같은 책을 다시 담기"""
    book = await _book(session, library_a.id)
    await me.put(f"/basket/{book['id']}")
    await _age(session, minutes=30)
    first = (await me.get("/basket")).json()["books"][0]["added_at"]
    assert (await me.put(f"/basket/{book['id']}")).status_code == 204
    books = (await me.get("/basket")).json()["books"]
    assert len(books) == 1 and books[0]["added_at"] == first
    assert await _rows(session) == 1


async def test_remove_then_add_again_is_new_time(
    me: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/member-basket] 담은 책 보관과 불러오기 / 담았다 빼고 다시 담기"""
    book = await _book(session, library_a.id)
    await me.put(f"/basket/{book['id']}")
    await _age(session, hours=2)
    old = (await me.get("/basket")).json()["books"][0]["added_at"]
    await me.delete(f"/basket/{book['id']}")
    await me.put(f"/basket/{book['id']}")
    assert (await me.get("/basket")).json()["books"][0]["added_at"] > old


async def test_resume_after_login_again(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant, member: dict
) -> None:
    """[circulation/member-basket] 담은 책 보관과 불러오기 / 다시 로그인해도 이어짐"""
    book = await _book(session, library_a.id)
    await login_member(kiosk_client, PHONE)
    await kiosk_client.put(f"/basket/{book['id']}")
    kiosk_client.headers.pop(HEADER)
    await kiosk_client.post("/auth/member-logout")  # 토큰 없이도 조용히 끝난다
    await login_member(kiosk_client, PHONE)
    assert await _ids(kiosk_client) == [book["id"]]


async def test_member_value_in_request_is_ignored(
    me: AsyncClient, session: AsyncSession, library_a: Tenant, member: dict
) -> None:
    """[circulation/member-basket] 담은 책 보관과 불러오기 / 본문·쿼리의 회원 값은 무시"""
    other = await add_member(session, library_a.id, "M0002", phone=PHONE_Y)
    book = await _book(session, library_a.id)
    res = await me.put(f"/basket/{book['id']}?member_id={other['id']}", json={"member_id": 99})
    assert res.status_code == 204
    owners = list(await session.scalars(text("SELECT member_id FROM basket_items")))
    assert owners == [member["id"]]


# --- 회원 세션 ---


async def test_requires_member_session(kiosk_client: AsyncClient, member: dict) -> None:
    """[circulation/member-basket] 회원 세션이 필요함 / 회원 토큰 없음"""
    for call in (
        kiosk_client.get("/basket"),
        kiosk_client.put("/basket/1"),
        kiosk_client.delete("/basket/1"),
        kiosk_client.delete("/basket"),
    ):
        res = await call
        assert res.status_code == 403
        assert res.json()["detail"] == REQUIRED


async def test_ended_member_session(
    me: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/member-basket] 회원 세션이 필요함 / 끝난 회원 세션"""
    book = await _book(session, library_a.id)
    await me.post("/auth/member-logout", headers={HEADER: me.headers[HEADER]})
    assert (await me.put(f"/basket/{book['id']}")).status_code == 403
    assert await _rows(session) == 0


async def test_staff_token_error_is_401(session: AsyncSession, member: dict) -> None:
    """[circulation/member-basket] 회원 세션이 필요함 / 직원 토큰 오류"""
    async with make_client() as anonymous:
        assert (await anonymous.get("/basket")).status_code == 401
    async with make_client("not-a-token") as wrong:
        assert (await wrong.get("/basket", headers={HEADER: "x"})).status_code == 401


async def test_admin_token_alone_is_403(admin_client: AsyncClient, member: dict) -> None:
    """[circulation/member-basket] 어디에도 쓰지 않음 / 관리자는 볼 수 없음"""
    assert (await admin_client.get("/basket")).status_code == 403


async def test_member_session_of_other_kiosk_session(
    me: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/member-basket] 회원 세션이 필요함 / 다른 키오스크 세션의 회원 토큰"""
    token = me.headers[HEADER]
    other = await add_staff_session(session, library_a.kiosk)
    async with make_client(other) as second:
        res = await second.get("/basket", headers={HEADER: token})
    assert res.status_code == 403


# --- 기관과 회원의 분리 ---


async def test_other_library_book_is_404(
    me: AsyncClient, session: AsyncSession, library_b: Tenant
) -> None:
    """[circulation/member-basket] 기관과 회원의 분리 / 다른 기관 책 담기"""
    foreign = await _book(session, library_b.id)
    res = await me.put(f"/basket/{foreign['id']}")
    assert res.status_code == 404
    assert str(foreign["id"]) not in res.text and PHONE not in res.text
    assert await _rows(session) == 0


async def test_other_member_does_not_see(
    kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant, member: dict
) -> None:
    """[circulation/member-basket] 기관과 회원의 분리 / 다른 회원의 담은 책"""
    await add_member(session, library_a.id, "M0002", phone=PHONE_Y)
    book = await _book(session, library_a.id)
    await login_member(kiosk_client, PHONE)
    await kiosk_client.put(f"/basket/{book['id']}")
    await login_member(kiosk_client, PHONE_Y)
    assert await _ids(kiosk_client) == []
    await kiosk_client.delete("/basket")  # 남의 것은 지워지지 않는다
    assert await _rows(session) == 1


async def test_other_library_member_does_not_see(
    kiosk_client: AsyncClient,
    kiosk_client_b: AsyncClient,
    session: AsyncSession,
    library_a: Tenant,
    library_b: Tenant,
    member: dict,
) -> None:
    """[circulation/member-basket] 기관과 회원의 분리 / 다른 기관의 담은 책 (같은 번호)"""
    await add_member(session, library_b.id, "B0001", phone=PHONE)
    book = await _book(session, library_a.id)
    await login_member(kiosk_client, PHONE)
    await kiosk_client.put(f"/basket/{book['id']}")
    await login_member(kiosk_client_b, PHONE)
    assert await _ids(kiosk_client_b) == []


async def test_remove_other_library_book_changes_nothing(
    me: AsyncClient, session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[circulation/member-basket] 기관과 회원의 분리 / 다른 기관 책 빼기"""
    mine = await _book(session, library_a.id)
    foreign = await _book(session, library_b.id)
    await me.put(f"/basket/{mine['id']}")
    assert (await me.delete(f"/basket/{foreign['id']}")).status_code == 204
    assert await _ids(me) == [mine["id"]]


# --- 담을 수 있는 책 ---


async def test_unknown_book_is_404(me: AsyncClient) -> None:
    """[circulation/member-basket] 담을 수 있는 책 / 없는 책"""
    assert (await me.put("/basket/999999")).status_code == 404


async def test_withdrawn_book_is_404(
    me: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/member-basket] 담을 수 있는 책 / 소장에서 빠진 책"""
    book = await _book(session, library_a.id, "withdrawn")
    assert (await me.put(f"/basket/{book['id']}")).status_code == 404
    assert await _rows(session) == 0


async def test_on_loan_book_can_be_added(
    me: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/member-basket] 담을 수 있는 책 / 모두 대출 중인 책"""
    book = await _book(session, library_a.id, "on_loan")
    assert (await me.put(f"/basket/{book['id']}")).status_code == 204
    shown = (await me.get("/basket")).json()["books"][0]
    assert shown["available_count"] == 0 and shown["on_loan_count"] == 1


# --- 보관 3시간 ---


async def test_keep_three_hours(me: AsyncClient, session: AsyncSession, library_a: Tenant) -> None:
    """[circulation/member-basket] 보관 3시간 / 3시간 안, 3시간 뒤"""
    assert get_settings().basket_keep_hours == 3
    book = await _book(session, library_a.id)
    await me.put(f"/basket/{book['id']}")
    await _age(session, hours=2, minutes=59)
    assert await _ids(me) == [book["id"]]
    await _age(session, hours=3, minutes=1)
    assert await _ids(me) == []
    assert await _rows(session) == 1  # 읽을 때는 거르기만 한다


async def test_purge_expired_removes_only_old(
    me: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/member-basket] 보관 3시간 / 정리 작업"""
    old = await _book(session, library_a.id, isbn=None, title="오래된 책")
    fresh = await _book(session, library_a.id, isbn=None, title="새 책")
    await me.put(f"/basket/{old['id']}")
    await _age(session, hours=3, minutes=1)
    await me.put(f"/basket/{fresh['id']}")
    assert await basket_service.purge_expired(session) == 1
    assert await _ids(me) == [fresh["id"]]
    assert await _rows(session) == 1


async def test_periodic_purge_runs_basket_even_if_session_purge_fails(
    me: AsyncClient, session: AsyncSession, library_a: Tenant, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[circulation/member-basket] 보관 3시간 / 정리 작업 (1분 주기 작업이 함께 지운다)"""
    book = await _book(session, library_a.id)
    await me.put(f"/basket/{book['id']}")
    await _age(session, hours=4)

    async def broken(_session: AsyncSession) -> int:
        raise RuntimeError("session purge failed")

    monkeypatch.setattr(chat, "purge_expired", broken)
    opened = 0
    done = asyncio.Event()

    @contextlib.asynccontextmanager
    async def open_session():
        nonlocal opened
        opened += 1
        yield session
        if opened == 2:
            done.set()

    task = asyncio.create_task(chat.purge_forever(open_session, interval=3600))
    try:
        await asyncio.wait_for(done.wait(), timeout=5)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    assert await _rows(session) == 0


async def test_adding_again_does_not_extend(
    me: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/member-basket] 보관 3시간 / 다시 담아도 늘지 않음"""
    book = await _book(session, library_a.id)
    await me.put(f"/basket/{book['id']}")
    await _age(session, hours=2)
    await me.put(f"/basket/{book['id']}")
    await _age(session, hours=3, seconds=1)
    assert await _ids(me) == []


async def test_expired_row_does_not_block_adding(
    me: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/member-basket] 보관 3시간 / 끝났지만 지워지지 않은 줄 위에 다시 담기"""
    book = await _book(session, library_a.id)
    await me.put(f"/basket/{book['id']}")
    await _age(session, hours=4)
    assert (await me.put(f"/basket/{book['id']}")).status_code == 204
    assert await _ids(me) == [book["id"]]
    assert await _rows(session) == 1


# --- 담을 수 있는 권수 ---


async def _fill(me: AsyncClient, session: AsyncSession, library_id: int, n: int) -> list[int]:
    ids = []
    for i in range(n):
        book = await _book(session, library_id, isbn=None, title=f"책 {i}")
        assert (await me.put(f"/basket/{book['id']}")).status_code == 204
        ids.append(book["id"])
    return ids


async def test_limit_ten(me: AsyncClient, session: AsyncSession, library_a: Tenant) -> None:
    """[circulation/member-basket] 담을 수 있는 권수 / 11권째, 10권일 때 같은 책, 빼면 담김"""
    assert get_settings().basket_limit == 10
    ids = await _fill(me, session, library_a.id, 10)
    extra = await _book(session, library_a.id, isbn=None, title="열한 번째")
    res = await me.put(f"/basket/{extra['id']}")
    assert res.status_code == 409 and "10권" in res.json()["detail"]
    assert await _ids(me) == ids
    assert (await me.put(f"/basket/{ids[0]}")).status_code == 204
    await me.delete(f"/basket/{ids[0]}")
    assert (await me.put(f"/basket/{extra['id']}")).status_code == 204
    assert len(await _ids(me)) == 10


async def test_hidden_books_count_toward_limit(
    me: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/member-basket] 담을 수 있는 권수 / 숨겨진 책도 권수에 센다"""
    ids = await _fill(me, session, library_a.id, 10)
    await session.execute(text("UPDATE holdings SET status = 'withdrawn'"))
    assert await _ids(me) == []
    extra = await _book(session, library_a.id, isbn=None, title="새 책")
    assert (await me.put(f"/basket/{extra['id']}")).status_code == 409
    assert len(ids) == 10


async def test_expired_rows_do_not_count_toward_limit(
    me: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/member-basket] 담을 수 있는 권수 / 끝난 줄은 세지 않는다"""
    await _fill(me, session, library_a.id, 10)
    await _age(session, hours=4)
    extra = await _book(session, library_a.id, isbn=None, title="새 책")
    assert (await me.put(f"/basket/{extra['id']}")).status_code == 204


# --- 빼기와 비우기 ---


async def test_remove_and_clear(me: AsyncClient, session: AsyncSession, library_a: Tenant) -> None:
    """[circulation/member-basket] 빼기와 비우기 / 한 권 빼기, 담기지 않은 책 빼기, 비우기"""
    ids = await _fill(me, session, library_a.id, 2)
    assert (await me.delete(f"/basket/{ids[0]}")).status_code == 204
    assert await _ids(me) == [ids[1]]
    assert (await me.delete("/basket/999999")).status_code == 204
    assert (await me.delete("/basket")).status_code == 204
    assert (await me.delete("/basket")).status_code == 204  # 이미 비어 있어도
    assert await _ids(me) == []


# --- 지금 상태로 보여 줌 ---


async def test_shows_current_state(
    me: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/member-basket] 지금 상태로 보여 줌 / 대출 상태가 바뀜, 소장에서 빠짐, 돌아옴"""
    book = await _book(session, library_a.id)
    await me.put(f"/basket/{book['id']}")
    await session.execute(text("UPDATE holdings SET status = 'on_loan'"))
    shown = (await me.get("/basket")).json()["books"][0]
    assert (shown["available_count"], shown["on_loan_count"]) == (0, 1)
    await session.execute(text("UPDATE holdings SET status = 'withdrawn'"))
    assert await _ids(me) == []
    assert await _rows(session) == 1  # 읽기는 줄을 지우지 않는다
    await session.execute(text("UPDATE holdings SET status = 'available'"))
    assert await _ids(me) == [book["id"]]


async def test_external_library_has_synced_time(
    session: AsyncSession, library_b: Tenant, kiosk_client_b: AsyncClient
) -> None:
    """[circulation/member-basket] 지금 상태로 보여 줌 / 외부 대출 기관의 갱신 시각"""
    await add_member(session, library_b.id, "B0001", phone=PHONE)
    synced = clock.now() - timedelta(days=1)
    book = await add_held_book(session, library_b.id, "available", synced=[synced])
    await login_member(kiosk_client_b, PHONE)
    await kiosk_client_b.put(f"/basket/{book['id']}")
    shown = (await kiosk_client_b.get("/basket")).json()["books"][0]
    assert shown["status_synced_at"] is not None


# --- 회원 값이 없음 ---


async def test_no_member_values_in_responses(
    me: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/member-basket] 응답에 회원 값이 없음 / 응답 필드, 오류 메시지"""
    book = await _book(session, library_a.id)
    await me.put(f"/basket/{book['id']}")
    text_body = (await me.get("/basket")).text
    for value in ("M0001", "김비밀", PHONE, "member_id", "member_number"):
        assert value not in text_body
    errors = [await me.put("/basket/999999"), await me.put("/basket/abc")]
    errors.append(await make_client().get("/basket"))
    for res in errors:
        for value in ("M0001", "김비밀", PHONE):
            assert value not in res.text


# --- 회원·기관 도서를 지우면 ---


async def test_deleting_member_removes_basket(
    me: AsyncClient,
    admin_client: AsyncClient,
    session: AsyncSession,
    library_a: Tenant,
    member: dict,
) -> None:
    """[circulation/member-basket] 회원을 지우면 담은 책도 지운다 / 회원 삭제"""
    await _fill(me, session, library_a.id, 2)
    assert (await admin_client.delete(f"/members/{member['id']}")).status_code == 204
    assert await _rows(session) == 0


# --- 기록이 늘지 않음 ---


async def test_no_records_created(
    me: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[circulation/member-basket] 어디에도 쓰지 않음 / 기록이 늘지 않음"""
    tables = (
        "recommendation_events",
        "agent_runs",
        "agent_steps",
        "chat_sessions",
        "chat_messages",
    )

    async def counts() -> list[int]:
        return [await session.scalar(text(f"SELECT count(*) FROM {t}")) for t in tables]

    before = await counts()
    book = await _book(session, library_a.id)
    await me.put(f"/basket/{book['id']}")
    await me.get("/basket")
    await me.delete(f"/basket/{book['id']}")
    await me.delete("/basket")
    assert await counts() == before
