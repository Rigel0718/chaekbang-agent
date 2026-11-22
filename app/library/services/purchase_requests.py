"""구매 요청서 service: 요청서·항목 관리, 승인 흐름(확정), 정가 조회로 계산한 금액.

관리 REST(`api/purchase_requests.py`)와 운영 에이전트의 `draft_purchase_request` tool이 이 함수들을
부른다. 승인 틀의 확정하는 종류(`CONFIRMING`)를 따른다. 정가는 예산 추정과 공적 보고용 기록이라

- 확정 전 상세는 정가를 조회해 금액을 응답에만 담고 저장하지 않는다(`request_detail`).
- 승인은 트랜잭션 밖에서 모든 항목의 정가를 다시 조회한 뒤, 같은 트랜잭션에서 금액을 기록하고
  희망도서를 닫고 확정한다(`approve_request`). 조회에 실패하면 아무것도 바꾸지 않는다.

금액은 `price_items` 한 곳에서 int(원)로 계산하고 LLM은 보지 않는다. 회원 값은 이 파일에 없다.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.list_prices import ListPriceLookup, PriceLookupUnavailable
from app.core import clock
from app.core.errors import ConflictError, UnavailableError
from app.core.tenancy import get_owned
from app.library.approval import (
    CONFIRMING,
    Action,
    ApprovalStatus,
    mark_executed,
    require_status,
    transition,
)
from app.library.models.book_request import BookRequest, BookRequestStatus
from app.library.models.purchase_request import PriceSource, PurchaseRequest, PurchaseRequestItem
from app.library.schemas.purchase_request import (
    ItemRead,
    PriceEstimate,
    PurchaseRequestDetail,
    PurchaseRequestRead,
    PurchaseRequestWrite,
)

LABEL = "구매 요청서"
PRICE_UNAVAILABLE = "정가 조회를 지금 쓸 수 없습니다. 잠시 뒤 다시 시도해 주세요"
CHANGED_WHILE_PRICING = "가격을 조회하는 동안 요청서가 바뀌었습니다. 다시 승인해 주세요"


@dataclass(frozen=True)
class PricedItem:
    isbn: str
    unit_price: int | None
    amount: int | None


@dataclass(frozen=True)
class Priced:
    items: list[PricedItem]
    total: int  # 가격을 찾은 항목 금액의 합
    missing_isbns: list[str]


def price_items(lines: Sequence[tuple[str, int]], prices: Mapping[str, int | None]) -> Priced:
    """항목 (ISBN, 권수)와 조회한 정가로 금액을 계산한다. 항목 금액은 정가 × 권수, 총액은 그 합이다.

    상세와 승인이 함께 쓰는 유일한 계산이다. 정가가 없는 ISBN은 단가·금액이 None이고 총액에서 뺀다.
    """
    items: list[PricedItem] = []
    missing: list[str] = []
    total = 0
    for isbn, quantity in lines:
        unit = prices.get(isbn)
        if unit is None:
            items.append(PricedItem(isbn, None, None))
            missing.append(isbn)
            continue
        amount = unit * quantity
        total += amount
        items.append(PricedItem(isbn, unit, amount))
    return Priced(items=items, total=total, missing_isbns=missing)


def _items(library_id: int, data: PurchaseRequestWrite) -> list[PurchaseRequestItem]:
    return [
        PurchaseRequestItem(
            library_id=library_id,
            position=position,
            isbn=item.isbn,
            title=item.title,
            author=item.author,
            quantity=item.quantity,
            reason_kind=item.reason_kind,
            reason=item.reason,
        )
        for position, item in enumerate(data.items, start=1)
    ]


def _lines(request: PurchaseRequest) -> list[tuple[str, int]]:
    return [(item.isbn, item.quantity) for item in request.items]


def to_read(request: PurchaseRequest) -> PurchaseRequestRead:
    return PurchaseRequestRead(
        id=request.id,
        title=request.title,
        vendor_name=request.vendor_name,
        note=request.note,
        status=request.status,
        item_count=len(request.items),
        created_by=request.created_by,
        approved_by=request.approved_by,
        approved_at=request.approved_at,
        confirmed_at=request.executed_at,
        rejected_reason=request.rejected_reason,
        total_amount=request.total_amount,
        priced_at=request.priced_at,
        price_source=request.price_source,
        created_at=request.created_at,
        updated_at=request.updated_at,
    )


def _detail(request: PurchaseRequest) -> PurchaseRequestDetail:
    return PurchaseRequestDetail(
        **to_read(request).model_dump(),
        items=[ItemRead.model_validate(item) for item in request.items],
        estimate=None,
    )


async def get_request(session: AsyncSession, library_id: int, request_id: int) -> PurchaseRequest:
    return await get_owned(session, PurchaseRequest, library_id, request_id, label=LABEL)


async def _reload(session: AsyncSession, library_id: int, request_id: int) -> PurchaseRequest:
    """Core UPDATE로 바뀐 상태를 ORM 객체에 다시 읽는다."""
    row = await session.scalar(
        select(PurchaseRequest)
        .where(PurchaseRequest.id == request_id, PurchaseRequest.library_id == library_id)
        .execution_options(populate_existing=True)
    )
    assert row is not None
    return row


async def create_request(
    session: AsyncSession,
    library_id: int,
    staff_id: int | None,
    data: PurchaseRequestWrite,
    *,
    submit: bool = False,
) -> PurchaseRequest:
    """초안을 만든다. `submit`이면 같은 트랜잭션에서 승인 대기로 올린다(운영 에이전트 tool)."""
    request = PurchaseRequest(
        library_id=library_id,
        title=data.title,
        vendor_name=data.vendor_name,
        note=data.note,
        created_by=staff_id,
        items=_items(library_id, data),
    )
    session.add(request)
    await session.flush()
    if submit:
        await transition(
            session, PurchaseRequest, CONFIRMING, library_id, request.id, Action.SUBMIT, label=LABEL
        )
    await session.commit()
    return await _reload(session, library_id, request.id)


async def update_request(
    session: AsyncSession, library_id: int, request_id: int, data: PurchaseRequestWrite
) -> PurchaseRequest:
    """초안의 내용을 통째로 바꾼다. 초안이 아니면 409."""
    request = await get_request(session, library_id, request_id)
    require_status(request, ApprovalStatus.DRAFT, label=LABEL, doing="고칠")
    request.title = data.title
    request.vendor_name = data.vendor_name
    request.note = data.note
    request.items.clear()
    await session.flush()
    request.items.extend(_items(library_id, data))
    await session.commit()
    return await _reload(session, library_id, request_id)


async def delete_request(session: AsyncSession, library_id: int, request_id: int) -> None:
    request = await get_request(session, library_id, request_id)
    require_status(request, ApprovalStatus.DRAFT, label=LABEL, doing="지울")
    await session.delete(request)
    await session.commit()


async def submit_request(
    session: AsyncSession, library_id: int, request_id: int
) -> PurchaseRequest:
    await transition(
        session, PurchaseRequest, CONFIRMING, library_id, request_id, Action.SUBMIT, label=LABEL
    )
    await session.commit()
    return await _reload(session, library_id, request_id)


async def reject_request(
    session: AsyncSession, library_id: int, request_id: int, reason: str
) -> PurchaseRequest:
    await transition(
        session,
        PurchaseRequest,
        CONFIRMING,
        library_id,
        request_id,
        Action.REJECT,
        label=LABEL,
        values={"rejected_reason": reason},
    )
    await session.commit()
    return await _reload(session, library_id, request_id)


async def list_requests(
    session: AsyncSession, library_id: int, status: ApprovalStatus | None = None
) -> list[PurchaseRequest]:
    """정가를 조회하지 않는다. 최신순."""
    query = select(PurchaseRequest).where(PurchaseRequest.library_id == library_id)
    if status is not None:
        query = query.where(PurchaseRequest.status == status)
    rows = await session.scalars(
        query.order_by(PurchaseRequest.created_at.desc(), PurchaseRequest.id.desc())
    )
    return list(rows)


async def request_detail(
    session: AsyncSession, library_id: int, request_id: int, lookup: ListPriceLookup
) -> PurchaseRequestDetail:
    """상세. 확정 전이면 그때 정가를 조회해 추정 금액을 응답에만 담고 저장하지 않는다.

    조회가 길어질 수 있어서(항목마다 외부 호출) 읽기를 끝낸 뒤 조회한다. 조회를 쓸 수 없으면
    200으로 금액 없이 돌려주고 `unavailable`을 켠다. 확정본은 조회하지 않고 기록한 값을 돌려준다.
    """
    request = await get_request(session, library_id, request_id)
    detail = _detail(request)
    if request.status == ApprovalStatus.CONFIRMED:
        return detail
    lines = _lines(request)
    await session.commit()  # 읽기 트랜잭션을 끝내고 연결을 놓는다
    try:
        prices = await lookup.lookup([isbn for isbn, _ in lines])
    except PriceLookupUnavailable:
        detail.estimate = PriceEstimate(
            estimated_total=None, missing_price_count=len(lines), priced_at=None, unavailable=True
        )
        return detail
    priced = price_items(lines, prices)
    detail.items = [
        item.model_copy(update={"unit_price": p.unit_price, "amount": p.amount})
        for item, p in zip(detail.items, priced.items, strict=True)
    ]
    detail.estimate = PriceEstimate(
        estimated_total=priced.total,
        missing_price_count=len(priced.missing_isbns),
        priced_at=clock.now(),
        unavailable=False,
    )
    return detail


async def approve_request(
    session: AsyncSession,
    library_id: int,
    request_id: int,
    staff_id: int | None,
    lookup: ListPriceLookup,
) -> PurchaseRequest:
    """승인하고 같은 트랜잭션에서 금액을 기록·희망도서를 닫고 확정한다.

    1. 승인 대기인지 읽고 읽기 트랜잭션을 끝낸다.
    2. 트랜잭션 밖에서 모든 항목의 정가를 조회한다. 장애면 503, 가격 없는 항목이 있으면 409이고
       두 경우 모두 아무것도 바뀌지 않는다.
    3. 조건부 갱신으로 승인하고, 조회하는 동안 항목이 바뀌지 않았는지 확인한 뒤 금액을 기록하고
       희망도서를 닫아 확정한다.
    """
    request = await get_request(session, library_id, request_id)
    require_status(request, ApprovalStatus.PENDING_APPROVAL, label=LABEL, doing="승인할")
    lines = _lines(request)
    await session.commit()

    try:
        prices = await lookup.lookup([isbn for isbn, _ in lines])
    except PriceLookupUnavailable:
        raise UnavailableError(PRICE_UNAVAILABLE) from None
    priced = price_items(lines, prices)
    if priced.missing_isbns:
        raise ConflictError(
            f"정가를 찾지 못한 항목이 있어 승인할 수 없습니다: {', '.join(priced.missing_isbns)}"
        )

    now = clock.now()
    await transition(
        session,
        PurchaseRequest,
        CONFIRMING,
        library_id,
        request_id,
        Action.APPROVE,
        label=LABEL,
        values={
            "approved_by": staff_id,
            "approved_at": now,
            "rejected_reason": None,
            "total_amount": priced.total,
            "priced_at": now,
            "price_source": PriceSource.YES24_LIST_PRICE,
        },
    )
    current = await _reload(session, library_id, request_id)
    if sorted(_lines(current)) != sorted(lines):
        await session.rollback()
        raise ConflictError(CHANGED_WHILE_PRICING)
    by_isbn = {p.isbn: p for p in priced.items}
    for item in current.items:
        item.unit_price = by_isbn[item.isbn].unit_price
        item.amount = by_isbn[item.isbn].amount
    await session.execute(
        update(BookRequest)
        .where(
            BookRequest.library_id == library_id,
            BookRequest.status == BookRequestStatus.REQUESTED,
            BookRequest.isbn.in_(by_isbn),
        )
        .values(
            status=BookRequestStatus.CLOSED,
            closed_at=now,
            purchase_request_id=request_id,
        )
        .execution_options(synchronize_session=False)
    )
    await mark_executed(session, PurchaseRequest, CONFIRMING, library_id, request_id, now)
    await session.commit()
    return await _reload(session, library_id, request_id)
