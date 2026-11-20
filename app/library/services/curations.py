"""큐레이션 service: 만들기·고치기·지우기, 승인 흐름, 게시본 읽기.

관리 REST(`api/curations.py`), 운영 에이전트의 `draft_curation`, AI 사서의 `get_curations`가
이 함수들을 부른다. 상태 전이는 공통 승인 틀(`app/library/approval.py`)을 따르고, 승인하면 같은
트랜잭션에서 게시한다. 책은 쓸 때 그 기관의 추천 가능한 책인지 보고, 게시본을 읽을 때 지금 추천
가능한 책만 다시 남긴다(저장된 책은 바꾸지 않는다).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.errors import ConflictError, NotFoundError
from app.core.tenancy import get_owned
from app.library.approval import (
    PUBLISHING,
    Action,
    ApprovalStatus,
    mark_executed,
    require_status,
    transition,
)
from app.library.models.curation import Curation, CurationItem
from app.library.recommendation.cards import shelf_of, summary_values
from app.library.recommendation.search import get_candidates
from app.library.schemas.curation import CurationBook, CurationWrite

LABEL = "큐레이션"
PUBLISHED_LIMIT = 5


async def _check_books(session: AsyncSession, library_id: int, ids: Sequence[int]) -> None:
    """모든 책이 그 기관의 추천 가능한 책인지 본다. 없거나 다른 기관이면 404, 추천 불가면 409."""
    candidates = await get_candidates(session, library_id, ids)
    missing = [i for i in ids if i not in candidates]
    if missing:
        raise NotFoundError(f"이 도서관에 없는 책입니다: {_ids(missing)}")
    blocked = [i for i in ids if not candidates[i].recommendable]
    if blocked:
        raise ConflictError(
            f"대출 가능하거나 대출 중인 사본이 없어 담을 수 없는 책입니다: {_ids(blocked)}"
        )


def _ids(ids: Sequence[int]) -> str:
    return ", ".join(str(i) for i in ids)


def _items(library_id: int, data: CurationWrite) -> list[CurationItem]:
    return [
        CurationItem(
            library_id=library_id,
            position=position,
            library_book_id=item.library_book_id,
            reason=item.reason,
        )
        for position, item in enumerate(data.items, start=1)
    ]


async def get_curation(session: AsyncSession, library_id: int, curation_id: int) -> Curation:
    return await get_owned(session, Curation, library_id, curation_id, label=LABEL)


async def _reload(session: AsyncSession, library_id: int, curation_id: int) -> Curation:
    """Core UPDATE로 바뀐 상태를 ORM 객체에 다시 읽는다."""
    row = await session.scalar(
        select(Curation)
        .where(Curation.id == curation_id, Curation.library_id == library_id)
        .execution_options(populate_existing=True)
    )
    assert row is not None
    return row


async def create_curation(
    session: AsyncSession,
    library_id: int,
    staff_id: int | None,
    data: CurationWrite,
    *,
    submit: bool = False,
) -> Curation:
    """초안을 만든다. `submit`이면 같은 트랜잭션에서 승인 대기로 올린다(운영 에이전트 tool)."""
    await _check_books(session, library_id, [i.library_book_id for i in data.items])
    curation = Curation(
        library_id=library_id,
        title=data.title,
        intro=data.intro,
        created_by=staff_id,
        items=_items(library_id, data),
    )
    session.add(curation)
    await session.flush()
    if submit:
        await transition(
            session, Curation, PUBLISHING, library_id, curation.id, Action.SUBMIT, label=LABEL
        )
    await session.commit()
    return await _reload(session, library_id, curation.id)


async def update_curation(
    session: AsyncSession, library_id: int, curation_id: int, data: CurationWrite
) -> Curation:
    """초안의 내용을 통째로 바꾼다. 초안이 아니면 409."""
    curation = await get_curation(session, library_id, curation_id)
    require_status(curation, ApprovalStatus.DRAFT, label=LABEL, doing="고칠")
    await _check_books(session, library_id, [i.library_book_id for i in data.items])
    curation.title = data.title
    curation.intro = data.intro
    curation.items.clear()
    await session.flush()
    curation.items.extend(_items(library_id, data))
    await session.commit()
    return await _reload(session, library_id, curation_id)


async def delete_curation(session: AsyncSession, library_id: int, curation_id: int) -> None:
    curation = await get_curation(session, library_id, curation_id)
    require_status(curation, ApprovalStatus.DRAFT, label=LABEL, doing="지울")
    await session.delete(curation)
    await session.commit()


async def submit_curation(session: AsyncSession, library_id: int, curation_id: int) -> Curation:
    await transition(
        session, Curation, PUBLISHING, library_id, curation_id, Action.SUBMIT, label=LABEL
    )
    await session.commit()
    return await _reload(session, library_id, curation_id)


async def approve_curation(
    session: AsyncSession, library_id: int, curation_id: int, staff_id: int | None
) -> Curation:
    """승인하고 같은 트랜잭션에서 게시한다. 게시는 상태를 바꾸는 것뿐이라 실패할 일이 없다."""
    now = clock.now()
    await transition(
        session,
        Curation,
        PUBLISHING,
        library_id,
        curation_id,
        Action.APPROVE,
        label=LABEL,
        values={"approved_by": staff_id, "approved_at": now, "rejected_reason": None},
    )
    await mark_executed(session, Curation, PUBLISHING, library_id, curation_id, now)
    await session.commit()
    return await _reload(session, library_id, curation_id)


async def reject_curation(
    session: AsyncSession, library_id: int, curation_id: int, reason: str
) -> Curation:
    await transition(
        session,
        Curation,
        PUBLISHING,
        library_id,
        curation_id,
        Action.REJECT,
        label=LABEL,
        values={"rejected_reason": reason},
    )
    await session.commit()
    return await _reload(session, library_id, curation_id)


async def unpublish_curation(session: AsyncSession, library_id: int, curation_id: int) -> Curation:
    await transition(
        session, Curation, PUBLISHING, library_id, curation_id, Action.UNPUBLISH, label=LABEL
    )
    await session.commit()
    return await _reload(session, library_id, curation_id)


async def list_curations(
    session: AsyncSession, library_id: int, status: ApprovalStatus | None = None
) -> list[Curation]:
    query = select(Curation).where(Curation.library_id == library_id)
    if status is not None:
        query = query.where(Curation.status == status)
    return list(
        await session.scalars(query.order_by(Curation.created_at.desc(), Curation.id.desc()))
    )


async def curation_books(
    session: AsyncSession,
    library_id: int,
    items: Sequence[CurationItem],
    *,
    recommendable_only: bool,
) -> list[CurationBook]:
    """저장된 순서의 책 카드. `recommendable_only`면 지금 추천할 수 없는 책을 뺀다."""
    ids = [item.library_book_id for item in items]
    candidates = await get_candidates(session, library_id, ids)
    shelf = await shelf_of(session, library_id, ids)
    books = []
    for item in items:
        candidate = candidates.get(item.library_book_id)
        if candidate is None or (recommendable_only and not candidate.recommendable):
            continue
        books.append(
            CurationBook(
                **summary_values(candidate, shelf.get(item.library_book_id, (None, None))),
                reason=item.reason,
            )
        )
    return books


@dataclass(frozen=True)
class Published:
    curation: Curation
    books: list[CurationBook]


async def published_curations(session: AsyncSession, library_id: int) -> list[Published]:
    """게시본 최신 5개. 지금 추천할 수 있는 책만 남기고, 남는 책이 없는 큐레이션은 뺀다.

    상한은 거른 뒤에 센다(책이 모두 빠진 큐레이션 자리를 그다음 게시본이 채운다).
    """
    rows = await session.scalars(
        select(Curation)
        .where(Curation.library_id == library_id, Curation.status == ApprovalStatus.PUBLISHED)
        .order_by(Curation.executed_at.desc(), Curation.id.desc())
    )
    result: list[Published] = []
    for curation in rows:
        books = await curation_books(session, library_id, curation.items, recommendable_only=True)
        if books:
            result.append(Published(curation, books))
        if len(result) == PUBLISHED_LIMIT:
            break
    return result
