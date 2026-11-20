"""[library/approval-flow], [library/curations] 승인 틀과 큐레이션 service.

API 시나리오(권한, 기관 분리, 게시본 읽기 응답)는 tests/library/test_curations_api.py, 재시작 뒤
이어짐은 tests/library/test_curations_restart.py에 있다.
"""

import asyncio
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.library.approval import ApprovalStatus
from app.library.schemas.curation import CurationWrite
from app.library.services import curations as svc
from tests.conftest import Tenant
from tests.helpers import add_held_book, assert_sql_rejected


async def _books(session: AsyncSession, library_id: int, n: int = 3, *statuses: str) -> list[int]:
    return [
        (await add_held_book(session, library_id, *statuses, title=f"책 {i}"))["id"]
        for i in range(n)
    ]


def _write(ids: list[int], title: str = "공룡 특집", **extra: Any) -> CurationWrite:
    return CurationWrite(
        title=title,
        intro=extra.pop("intro", "공룡을 좋아하는 친구들에게"),
        items=[{"library_book_id": i, "reason": f"이유 {i}"} for i in ids],
        **extra,
    )


async def _pending(session: AsyncSession, tenant: Tenant, ids: list[int] | None = None):
    ids = ids or await _books(session, tenant.id)
    return await svc.create_curation(
        session, tenant.id, tenant.admin["id"], _write(ids), submit=True
    )


async def _published(session: AsyncSession, tenant: Tenant, ids: list[int] | None = None):
    curation = await _pending(session, tenant, ids)
    return await svc.approve_curation(session, tenant.id, curation.id, tenant.admin["id"])


# --- 승인 상태 ---


async def test_status_rejects_unknown_value(session: AsyncSession, library_a: Tenant) -> None:
    """[library/approval-flow] 승인 상태 / 허용되지 않은 상태 저장"""
    curation = await svc.create_curation(
        session, library_a.id, None, _write(await _books(session, library_a.id))
    )
    await assert_sql_rejected(
        session,
        "UPDATE curations SET status = 'rejected' WHERE id = :id",
        match="approval_status",
        id=curation.id,
    )


# --- 상태 전이 ---


async def test_submit(session: AsyncSession, library_a: Tenant) -> None:
    """[library/approval-flow] 상태 전이 / 제출"""
    curation = await svc.create_curation(
        session, library_a.id, None, _write(await _books(session, library_a.id))
    )
    assert curation.status == ApprovalStatus.DRAFT
    submitted = await svc.submit_curation(session, library_a.id, curation.id)
    assert submitted.status == ApprovalStatus.PENDING_APPROVAL


async def test_reject_returns_to_draft_with_reason(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[library/approval-flow] 상태 전이 / 반려"""
    curation = await _pending(session, library_a)
    rejected = await svc.reject_curation(session, library_a.id, curation.id, "책을 바꿔 주세요")
    assert rejected.status == ApprovalStatus.DRAFT
    assert rejected.rejected_reason == "책을 바꿔 주세요"


async def test_cannot_approve_draft(session: AsyncSession, library_a: Tenant) -> None:
    """[library/approval-flow] 상태 전이 / 초안을 바로 승인"""
    curation = await svc.create_curation(
        session, library_a.id, None, _write(await _books(session, library_a.id))
    )
    with pytest.raises(ConflictError):
        await svc.approve_curation(session, library_a.id, curation.id, library_a.admin["id"])
    assert (await svc.get_curation(session, library_a.id, curation.id)).status == "draft"


async def test_cannot_edit_or_delete_pending(session: AsyncSession, library_a: Tenant) -> None:
    """[library/approval-flow] 상태 전이 / 승인 대기 중 수정"""
    ids = await _books(session, library_a.id, 4)
    curation = await _pending(session, library_a, ids[:3])
    with pytest.raises(ConflictError):
        await svc.update_curation(session, library_a.id, curation.id, _write(ids[1:], "바꿈"))
    with pytest.raises(ConflictError):
        await svc.delete_curation(session, library_a.id, curation.id)
    kept = await svc.get_curation(session, library_a.id, curation.id)
    assert kept.title == "공룡 특집"
    assert [i.library_book_id for i in kept.items] == ids[:3]


async def test_cannot_unpublish_pending(session: AsyncSession, library_a: Tenant) -> None:
    """[library/approval-flow] 상태 전이 / 게시본이 아닌 것을 내리기"""
    curation = await _pending(session, library_a)
    with pytest.raises(ConflictError):
        await svc.unpublish_curation(session, library_a.id, curation.id)


async def test_cannot_submit_twice_or_reject_draft(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[library/approval-flow] 상태 전이: 정해진 전이 밖은 409"""
    curation = await _pending(session, library_a)
    with pytest.raises(ConflictError):
        await svc.submit_curation(session, library_a.id, curation.id)
    rejected = await svc.reject_curation(session, library_a.id, curation.id, "다시")
    with pytest.raises(ConflictError):
        await svc.reject_curation(session, library_a.id, rejected.id, "또")


async def test_delete_draft(session: AsyncSession, library_a: Tenant) -> None:
    """[library/approval-flow] 상태 전이: 삭제는 초안에서 된다(포함 도서도 지운다)"""
    curation = await svc.create_curation(
        session, library_a.id, None, _write(await _books(session, library_a.id))
    )
    await svc.delete_curation(session, library_a.id, curation.id)
    with pytest.raises(NotFoundError):
        await svc.get_curation(session, library_a.id, curation.id)
    left = await session.scalar(
        text("SELECT count(*) FROM curation_items WHERE curation_id = :id"), {"id": curation.id}
    )
    assert left == 0


# --- 승인과 실행, 동시 승인 ---


async def test_approve_records_and_publishes(session: AsyncSession, library_a: Tenant) -> None:
    """[library/approval-flow] 승인과 실행 / 승인 기록"""
    curation = await _published(session, library_a)
    assert curation.status == ApprovalStatus.PUBLISHED
    assert curation.approved_by == library_a.admin["id"]
    assert curation.approved_at is not None
    assert curation.executed_at == curation.approved_at


async def test_double_approve(session: AsyncSession, library_a: Tenant) -> None:
    """[library/approval-flow] 동시 승인 / 두 번 승인"""
    curation = await _pending(session, library_a)
    first = await svc.approve_curation(session, library_a.id, curation.id, library_a.admin["id"])
    approved_at = first.approved_at
    with pytest.raises(ConflictError):
        await svc.approve_curation(session, library_a.id, curation.id, library_a.kiosk["id"])
    again = await svc.get_curation(session, library_a.id, curation.id)
    assert again.approved_by == library_a.admin["id"]
    assert again.approved_at == approved_at


async def test_concurrent_approve_and_reject(engine, library_a: Tenant) -> None:
    """[library/approval-flow] 동시 승인: 겹친 승인·반려 중 하나만 반영된다(다른 연결 둘)"""
    from sqlalchemy.ext.asyncio import AsyncSession as Session

    async with Session(engine, expire_on_commit=False) as setup:
        tenant = await _tenant_committed(setup)
        curation = await _pending(setup, tenant)
    try:

        async def approve():
            async with Session(engine, expire_on_commit=False) as s:
                await svc.approve_curation(s, tenant.id, curation.id, tenant.admin["id"])

        async def reject():
            async with Session(engine, expire_on_commit=False) as s:
                await svc.reject_curation(s, tenant.id, curation.id, "겹침")

        results = await asyncio.gather(approve(), reject(), return_exceptions=True)
        assert sum(isinstance(r, ConflictError) for r in results) == 1
        assert sum(r is None for r in results) == 1
    finally:
        async with Session(engine) as cleanup:
            await _drop_tenant(cleanup, tenant.id)


async def _tenant_committed(session: AsyncSession) -> Tenant:
    from tests.conftest import _tenant

    tenant = await _tenant(session, "동시 승인 도서관", "internal", "concurrent")
    await session.commit()
    return tenant


async def _drop_tenant(session: AsyncSession, library_id: int) -> None:
    for table in ("curations", "holdings", "library_books", "staff_sessions", "staff_users"):
        await session.execute(
            text(f"DELETE FROM {table} WHERE library_id = :id"), {"id": library_id}
        )
    await session.execute(text("DELETE FROM libraries WHERE id = :id"), {"id": library_id})
    await session.commit()


# --- 기관 분리(service) ---


async def test_other_library_transition_is_not_found(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[library/approval-flow] 승인의 기관 분리 / 다른 기관의 초안 승인"""
    curation = await _pending(session, library_b)
    with pytest.raises(NotFoundError):
        await svc.approve_curation(session, library_a.id, curation.id, library_a.admin["id"])
    kept = await svc.get_curation(session, library_b.id, curation.id)
    assert kept.status == ApprovalStatus.PENDING_APPROVAL


async def test_other_library_list(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[library/approval-flow] 승인의 기관 분리 / 다른 기관의 초안 목록"""
    mine = await _pending(session, library_a)
    await _pending(session, library_b)
    assert [c.id for c in await svc.list_curations(session, library_a.id)] == [mine.id]


# --- 큐레이션 내용 ---


def test_too_few_books() -> None:
    """[library/curations] 큐레이션 내용 / 권수 부족"""
    with pytest.raises(ValidationError):
        _write([1, 2])


def test_too_many_books() -> None:
    """[library/curations] 큐레이션 내용: 10권을 넘으면 거부"""
    with pytest.raises(ValidationError):
        _write(list(range(1, 12)))


def test_reason_too_long() -> None:
    """[library/curations] 큐레이션 내용 / 이유 길이 초과"""
    with pytest.raises(ValidationError):
        CurationWrite(
            title="t",
            items=[
                {"library_book_id": i, "reason": "가" * (61 if i == 1 else 5)} for i in (1, 2, 3)
            ],
        )


def test_title_and_intro_limits() -> None:
    """[library/curations] 큐레이션 내용: 제목 40자, 소개 200자"""
    with pytest.raises(ValidationError):
        _write([1, 2, 3], title="가" * 41)
    with pytest.raises(ValidationError):
        _write([1, 2, 3], intro="가" * 201)
    assert _write([1, 2, 3], intro=None).intro is None


async def test_duplicate_book_kept_once(session: AsyncSession, library_a: Tenant) -> None:
    """[library/curations] 큐레이션 내용 / 같은 책 두 번"""
    ids = await _books(session, library_a.id)
    data = CurationWrite(
        title="t",
        items=[
            {"library_book_id": ids[0], "reason": "처음"},
            {"library_book_id": ids[1], "reason": "둘"},
            {"library_book_id": ids[0], "reason": "다시"},
            {"library_book_id": ids[2], "reason": "셋"},
        ],
    )
    curation = await svc.create_curation(session, library_a.id, None, data)
    assert [(i.library_book_id, i.reason) for i in curation.items] == [
        (ids[0], "처음"),
        (ids[1], "둘"),
        (ids[2], "셋"),
    ]


# --- 추천 가능한 소장 도서 ---


async def test_withdrawn_only_book_rejected(session: AsyncSession, library_a: Tenant) -> None:
    """[library/curations] 큐레이션의 책은 추천 가능한 소장 도서 / 제적 사본만 있는 책"""
    ids = await _books(session, library_a.id, 2)
    withdrawn = (await add_held_book(session, library_a.id, "withdrawn", "lost"))["id"]
    with pytest.raises(ConflictError, match=str(withdrawn)):
        await svc.create_curation(session, library_a.id, None, _write([*ids, withdrawn]))
    assert await svc.list_curations(session, library_a.id) == []


async def test_other_library_book_not_found(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[library/curations] 큐레이션의 책은 추천 가능한 소장 도서 / 다른 기관의 책"""
    ids = await _books(session, library_a.id, 2)
    theirs = (await add_held_book(session, library_b.id))["id"]
    with pytest.raises(NotFoundError, match=str(theirs)):
        await svc.create_curation(session, library_a.id, None, _write([*ids, theirs]))


async def test_on_loan_book_allowed(session: AsyncSession, library_a: Tenant) -> None:
    """[library/curations] 큐레이션의 책은 추천 가능한 소장 도서: 대출 중 사본만 있어도 된다"""
    ids = await _books(session, library_a.id, 2)
    on_loan = (await add_held_book(session, library_a.id, "on_loan"))["id"]
    curation = await svc.create_curation(session, library_a.id, None, _write([*ids, on_loan]))
    assert len(curation.items) == 3


async def test_update_checks_books(session: AsyncSession, library_a: Tenant) -> None:
    """[library/curations] 큐레이션의 책은 추천 가능한 소장 도서: 고칠 때도 본다"""
    ids = await _books(session, library_a.id)
    curation = await svc.create_curation(session, library_a.id, None, _write(ids))
    lost = (await add_held_book(session, library_a.id, "lost"))["id"]
    with pytest.raises(ConflictError):
        await svc.update_curation(session, library_a.id, curation.id, _write([*ids[:2], lost]))


# --- 고친 뒤 제출, 승인하면 게시 ---


async def test_edit_after_reject_then_submit(session: AsyncSession, library_a: Tenant) -> None:
    """[library/curations] 큐레이션 관리 API / 고친 뒤 제출 (service)"""
    ids = await _books(session, library_a.id, 5)
    curation = await _pending(session, library_a, ids[:3])
    await svc.reject_curation(session, library_a.id, curation.id, "바꿔 주세요")
    await svc.update_curation(session, library_a.id, curation.id, _write(ids[2:], "새 제목"))
    submitted = await svc.submit_curation(session, library_a.id, curation.id)
    assert submitted.status == ApprovalStatus.PENDING_APPROVAL
    assert submitted.title == "새 제목"
    assert [i.library_book_id for i in submitted.items] == ids[2:]
    assert [i.position for i in submitted.items] == [1, 2, 3]


async def test_published_after_approve(session: AsyncSession, library_a: Tenant) -> None:
    """[library/curations] 승인하면 게시 / 승인 뒤 게시본"""
    curation = await _published(session, library_a)
    assert [p.curation.id for p in await svc.published_curations(session, library_a.id)] == [
        curation.id
    ]


async def test_unpublish(session: AsyncSession, library_a: Tenant) -> None:
    """[library/curations] 승인하면 게시 / 내리기"""
    curation = await _published(session, library_a)
    archived = await svc.unpublish_curation(session, library_a.id, curation.id)
    assert archived.status == ApprovalStatus.ARCHIVED
    assert await svc.published_curations(session, library_a.id) == []


# --- 게시본 읽기 ---


async def test_published_latest_five(session: AsyncSession, library_a: Tenant) -> None:
    """[library/curations] 게시본 읽기 / 최신 5개"""
    ids = await _books(session, library_a.id)
    made = []
    for n in range(6):
        curation = await _published(session, library_a, ids)
        await session.execute(
            text(
                "UPDATE curations SET executed_at = now() + make_interval(mins => :n)"
                " WHERE id = :id"
            ),
            {"n": n, "id": curation.id},
        )
        made.append(curation.id)
    shown = [p.curation.id for p in await svc.published_curations(session, library_a.id)]
    assert shown == list(reversed(made[1:]))


async def test_withdrawn_after_publish(session: AsyncSession, library_a: Tenant) -> None:
    """[library/curations] 읽을 때 다시 거르기 / 게시 뒤 제적"""
    ids = await _books(session, library_a.id)
    curation = await _published(session, library_a, ids)
    await session.execute(
        text("UPDATE holdings SET status = 'withdrawn' WHERE library_book_id = :id"),
        {"id": ids[1]},
    )
    [published] = await svc.published_curations(session, library_a.id)
    assert [b.library_book_id for b in published.books] == [ids[0], ids[2]]
    stored = await svc.get_curation(session, library_a.id, curation.id)
    books = await svc.curation_books(session, library_a.id, stored.items, recommendable_only=False)
    assert [b.library_book_id for b in books] == ids


async def test_all_books_gone(session: AsyncSession, library_a: Tenant) -> None:
    """[library/curations] 읽을 때 다시 거르기 / 모두 빠짐"""
    ids = await _books(session, library_a.id)
    await _published(session, library_a, ids)
    await session.execute(
        text("UPDATE holdings SET status = 'lost' WHERE library_id = :id"), {"id": library_a.id}
    )
    assert await svc.published_curations(session, library_a.id) == []


async def test_curation_book_card_values(session: AsyncSession, library_a: Tenant) -> None:
    """[library/curations] 게시본 읽기: 책 카드는 추천 카드와 같은 서지·대출 상태와 이유를 담는다"""
    ids = await _books(session, library_a.id, 2)
    on_loan = (await add_held_book(session, library_a.id, "on_loan", "available", title="공룡"))[
        "id"
    ]
    await _published(session, library_a, [*ids, on_loan])
    [published] = await svc.published_curations(session, library_a.id)
    card = published.books[2]
    assert (card.title, card.available_count, card.on_loan_count) == ("공룡", 1, 1)
    assert card.reason == f"이유 {on_loan}"
