"""[agent/recommendation-events] 추천 노출 기록."""

from httpx import AsyncClient
from sqlalchemy import inspect, select, text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.library.librarian import PROFILE_NAME
from app.library.models.chat import RecommendationEvent
from app.library.services import chat
from tests.agent.fakes import FakeLlm
from tests.conftest import Tenant
from tests.library.librarian_helpers import add_held_book, librarian, submit


async def _turn(session: AsyncSession, library_id: int, llm: FakeLlm) -> int:
    prepared = await chat.prepare_turn(
        session, library_id, None, "공룡 책", profile_name=PROFILE_NAME
    )
    events = [e async for e in chat.stream_turn(session, llm, librarian(), prepared)]
    return events[-1].data["run_id"]


async def _rows(session: AsyncSession, run_id: int) -> list[RecommendationEvent]:
    return list(
        await session.scalars(
            select(RecommendationEvent)
            .where(RecommendationEvent.run_id == run_id)
            .order_by(RecommendationEvent.position)
        )
    )


async def test_two_books(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/recommendation-events] 노출 기록 / 추천 두 권"""
    one = await add_held_book(session, library_a.id, title="공룡 가")
    two = await add_held_book(session, library_a.id, title="공룡 나")
    run_id = await _turn(session, library_a.id, FakeLlm([submit("둘 다요", one["id"], two["id"])]))
    rows = await _rows(session, run_id)
    assert [(r.position, r.library_book_id) for r in rows] == [(1, one["id"]), (2, two["id"])]
    assert {(r.run_id, r.library_id) for r in rows} == {(run_id, library_a.id)}
    assert all(r.shown_at is not None for r in rows)


async def test_was_available(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/recommendation-events] 노출 기록 / 대출 가능 여부"""
    on_loan = await add_held_book(session, library_a.id, "on_loan", title="공룡 가")
    free = await add_held_book(session, library_a.id, "available", "on_loan", title="공룡 나")
    run_id = await _turn(
        session, library_a.id, FakeLlm([submit("둘 다요", on_loan["id"], free["id"])])
    )
    assert [r.was_available for r in await _rows(session, run_id)] == [False, True]


async def test_only_shown_books(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/recommendation-events] 보인 추천만 기록 / 위반한 추천"""
    ours = await add_held_book(session, library_a.id, title="공룡 가")
    lost = await add_held_book(session, library_a.id, "lost", title="공룡 나")
    llm = FakeLlm([submit("둘 다요", lost["id"], ours["id"]), submit("이 책요", ours["id"])])
    run_id = await _turn(session, library_a.id, llm)
    assert [r.library_book_id for r in await _rows(session, run_id)] == [ours["id"]]


async def test_fallback_has_no_rows(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/recommendation-events] 보인 추천만 기록 / 고정 답"""
    lost = await add_held_book(session, library_a.id, "lost", title="공룡 나")
    bad = submit("이 책요", lost["id"])
    run_id = await _turn(session, library_a.id, FakeLlm([bad, bad, bad]))
    assert await _rows(session, run_id) == []


async def test_columns(engine: AsyncEngine) -> None:
    """[agent/recommendation-events] 기록하지 않는 값 / 세션과 잇지 않음"""
    async with engine.connect() as conn:
        columns = await conn.run_sync(
            lambda c: {col["name"] for col in inspect(c).get_columns("recommendation_events")}
        )
    assert columns == {
        "id",
        "library_id",
        "library_book_id",
        "run_id",
        "position",
        "was_available",
        "shown_at",
    }


async def test_delete_library_book_without_holdings(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/recommendation-events] 기관 도서 삭제와의 관계 / 사본 없는 도서 삭제"""
    book = await add_held_book(session, library_a.id, title="공룡 가")
    run_id = await _turn(session, library_a.id, FakeLlm([submit("이 책요", book["id"])]))
    assert len(await _rows(session, run_id)) == 1
    # 사본을 지워 사본 없는 도서로 만든다.
    await session.execute(
        text("DELETE FROM holdings WHERE library_book_id = :id"), {"id": book["id"]}
    )
    res = await admin_client.delete(f"/library-books/{book['id']}")
    assert res.status_code == 204
    assert await _rows(session, run_id) == []
