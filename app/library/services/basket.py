"""회원이 담은 책 보관. 책 id와 담은 시각만 두고, 담은 시각부터 정해진 시간이 지나면 사라진다.

추천·AI 사서·분석·노출 기록·대화 기록 어디에도 쓰지 않는다(`circulation/member-basket` 스펙).
이 파일에는 로그를 남기지 않는다. 회원은 항상 호출하는 쪽이 회원 세션에서 정해 넘긴다.
"""

from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import get_settings
from app.core.errors import ConflictError
from app.library.models.circulation import BasketItem
from app.library.recommendation.cards import shelf_of, summary_values
from app.library.recommendation.lookup import get_findable
from app.library.recommendation.search import get_candidates
from app.library.schemas.basket import BasketBook

LIMIT_MESSAGE = "담은 책은 {limit}권까지예요."


def _cutoff(now: datetime) -> datetime:
    """이 시각보다 오래전에 담은 줄은 끝난 줄이다."""
    return now - timedelta(hours=get_settings().basket_keep_hours)


def _mine(library_id: int, member_id: int):
    return (BasketItem.library_id == library_id, BasketItem.member_id == member_id)


async def add_book(
    session: AsyncSession, library_id: int, member_id: int, library_book_id: int
) -> None:
    """책을 담는다. 이미 담은 책이면 담은 시각을 그대로 두고 권수도 세지 않는다."""
    await get_findable(session, library_id, library_book_id)  # 없거나 소장에서 빠진 책은 404
    now = clock.now()
    cutoff = _cutoff(now)
    # 끝났지만 아직 지워지지 않은 같은 줄이 새로 담는 것을 막지 않게 먼저 지운다
    await session.execute(
        delete(BasketItem).where(
            *_mine(library_id, member_id),
            BasketItem.library_book_id == library_book_id,
            BasketItem.added_at <= cutoff,
        )
    )
    already = await session.scalar(
        select(BasketItem.id).where(
            *_mine(library_id, member_id),
            BasketItem.library_book_id == library_book_id,
        )
    )
    if already is None:
        count = await session.scalar(
            select(func.count())
            .select_from(BasketItem)
            .where(*_mine(library_id, member_id), BasketItem.added_at > cutoff)
        )
        limit = get_settings().basket_limit
        if (count or 0) >= limit:
            raise ConflictError(LIMIT_MESSAGE.format(limit=limit))
        # 같은 책을 동시에 담아도 한 줄이다(유일 제약, 늦은 쪽은 아무 일도 하지 않음)
        await session.execute(
            insert(BasketItem)
            .values(
                library_id=library_id,
                member_id=member_id,
                library_book_id=library_book_id,
                added_at=now,
            )
            .on_conflict_do_nothing(
                constraint="uq_basket_items_library_id_member_id_library_book_id"
            )
        )
    await session.commit()


async def remove_book(
    session: AsyncSession, library_id: int, member_id: int, library_book_id: int
) -> None:
    """한 권을 뺀다. 담겨 있지 않거나 다른 기관의 책 id여도 아무 일도 없다."""
    await session.execute(
        delete(BasketItem).where(
            *_mine(library_id, member_id), BasketItem.library_book_id == library_book_id
        )
    )
    await session.commit()


async def clear(session: AsyncSession, library_id: int, member_id: int) -> None:
    await session.execute(delete(BasketItem).where(*_mine(library_id, member_id)))
    await session.commit()


async def list_books(session: AsyncSession, library_id: int, member_id: int) -> list[BasketBook]:
    """담은 순서대로, 지금 상태의 책 값으로. 읽기만 한다(소장에서 빠진 책은 숨기고 줄은 둔다)."""
    rows = (
        await session.execute(
            select(BasketItem.library_book_id, BasketItem.added_at)
            .where(*_mine(library_id, member_id), BasketItem.added_at > _cutoff(clock.now()))
            .order_by(BasketItem.added_at, BasketItem.id)
        )
    ).all()
    candidates = await get_candidates(session, library_id, [book_id for book_id, _ in rows])
    shown = [
        (candidates[book_id], added_at)
        for book_id, added_at in rows
        if book_id in candidates and candidates[book_id].recommendable
    ]
    shelf = await shelf_of(session, library_id, [c.library_book.id for c, _ in shown])
    return [
        BasketBook(
            **summary_values(candidate, shelf.get(candidate.library_book.id, (None, None))),
            added_at=added_at,
        )
        for candidate, added_at in shown
    ]


async def purge_expired(session: AsyncSession) -> int:
    """보관 시간이 지난 줄을 모든 기관에서 지운다. 지운 줄 수를 돌려준다."""
    result = await session.execute(
        delete(BasketItem).where(BasketItem.added_at <= _cutoff(clock.now()))
    )
    await session.commit()
    return result.rowcount or 0
