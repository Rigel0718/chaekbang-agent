"""구매 요청서 API. 모두 관리자만, 로직은 service에 있다.

승인하면 같은 요청에서 정가를 조회해 금액을 기록하고 확정한다. 확정 전 상세는 정가를 조회해 추정
금액을 돌려주고 저장하지 않는다. 정가 조회기(YES24)는 `app.state`에 처음 쓸 때 만들고 서버가
끝날 때 닫는다. 키가 없어도 서버는 시작하고, 조회는 쓸 수 없다고 답한다.
"""

from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, FastAPI, Request, Response, status

from app.central.external.yes24 import definitions as yes24
from app.central.external.yes24.client import Yes24Client
from app.central.list_prices import ListPriceLookup, UnconfiguredListPrices, Yes24ListPrices
from app.core.config import get_settings
from app.library.analytics.periods import PeriodPreset
from app.library.approval import ApprovalStatus
from app.library.deps import AdminStaff, Session
from app.library.schemas.purchase_candidates import PurchaseCandidates
from app.library.schemas.purchase_request import (
    PurchaseRequestDetail,
    PurchaseRequestRead,
    PurchaseRequestWrite,
    RejectRequest,
)
from app.library.services import purchase_candidates
from app.library.services import purchase_requests as svc

router = APIRouter(prefix="/purchase-requests", tags=["purchase-requests"])


def get_list_prices(request: Request) -> ListPriceLookup:
    lookup = getattr(request.app.state, "list_prices", None)
    if lookup is None:
        settings = get_settings()
        if settings.yes24_api_key is None:
            lookup = UnconfiguredListPrices()
        else:
            http = httpx.AsyncClient(
                base_url=settings.yes24_base_url, timeout=yes24.REQUEST_TIMEOUT_SECONDS
            )
            request.app.state.list_prices_http = http
            lookup = Yes24ListPrices(Yes24Client(http, settings.yes24_api_key.get_secret_value()))
        request.app.state.list_prices = lookup
    return lookup


async def close_list_prices(app: FastAPI) -> None:
    http = getattr(app.state, "list_prices_http", None)
    if http is not None:
        await http.aclose()
    app.state.list_prices_http = app.state.list_prices = None


ListPrices = Annotated[ListPriceLookup, Depends(get_list_prices)]


@router.post("", status_code=status.HTTP_201_CREATED, response_model=PurchaseRequestRead)
async def create_request(data: PurchaseRequestWrite, staff: AdminStaff, session: Session):
    request = await svc.create_request(session, staff.library_id, staff.staff_id, data)
    return svc.to_read(request)


@router.get("", response_model=list[PurchaseRequestRead])
async def list_requests(staff: AdminStaff, session: Session, status: ApprovalStatus | None = None):
    """정가를 조회하지 않는다. 최신순."""
    rows = await svc.list_requests(session, staff.library_id, status)
    return [svc.to_read(row) for row in rows]


@router.get("/candidates", response_model=PurchaseCandidates)
async def candidates(staff: AdminStaff, session: Session, period: PeriodPreset | None = None):
    """희망도서(ISBN별)·인기·분야 숫자. 가격과 회원 값은 없다. `period`는 자체 대출 기관만 쓴다."""
    return await purchase_candidates.purchase_candidates(session, staff.library_id, period)


@router.get("/{request_id}", response_model=PurchaseRequestDetail)
async def get_request(request_id: int, staff: AdminStaff, session: Session, prices: ListPrices):
    """확정 전이면 YES24 정가를 조회해 추정 금액을 돌려준다(저장 안 함). 확정본은 기록한 금액."""
    return await svc.request_detail(session, staff.library_id, request_id, prices)


@router.put("/{request_id}", response_model=PurchaseRequestRead)
async def update_request(
    request_id: int, data: PurchaseRequestWrite, staff: AdminStaff, session: Session
):
    """초안의 내용을 통째로 바꾼다. 초안이 아니면 409."""
    request = await svc.update_request(session, staff.library_id, request_id, data)
    return svc.to_read(request)


@router.delete("/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_request(request_id: int, staff: AdminStaff, session: Session):
    await svc.delete_request(session, staff.library_id, request_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{request_id}/submit", response_model=PurchaseRequestRead)
async def submit_request(request_id: int, staff: AdminStaff, session: Session):
    request = await svc.submit_request(session, staff.library_id, request_id)
    return svc.to_read(request)


@router.post("/{request_id}/approve", response_model=PurchaseRequestRead)
async def approve_request(request_id: int, staff: AdminStaff, session: Session, prices: ListPrices):
    """정가를 다시 조회해 금액을 기록하고 확정한다. 가격 없는 항목이 있으면 409, 조회 장애면 503."""
    request = await svc.approve_request(
        session, staff.library_id, request_id, staff.staff_id, prices
    )
    return svc.to_read(request)


@router.post("/{request_id}/reject", response_model=PurchaseRequestRead)
async def reject_request(request_id: int, data: RejectRequest, staff: AdminStaff, session: Session):
    request = await svc.reject_request(session, staff.library_id, request_id, data.reason)
    return svc.to_read(request)
