"""큐레이션 API. 관리 경로는 관리자만, 게시본 읽기는 키오스크와 관리자. 로직은 service에 있다.

상태 전이(제출·승인·반려·내리기)는 공통 승인 틀을 따른다. 승인하면 같은 요청에서 게시한다.
"""

from fastapi import APIRouter, Response, status

from app.library.approval import ApprovalStatus
from app.library.deps import AdminStaff, CurrentStaff, Session
from app.library.models.curation import Curation
from app.library.schemas.curation import (
    CurationRead,
    CurationWrite,
    PublishedCuration,
    RejectRequest,
)
from app.library.services import curations as svc

router = APIRouter(prefix="/curations", tags=["curations"])
published_router = APIRouter(prefix="/librarian", tags=["librarian"])


async def _view(session: Session, library_id: int, curation: Curation) -> CurationRead:
    books = await svc.curation_books(session, library_id, curation.items, recommendable_only=False)
    return CurationRead(
        id=curation.id,
        title=curation.title,
        intro=curation.intro,
        status=curation.status,
        created_by=curation.created_by,
        approved_by=curation.approved_by,
        approved_at=curation.approved_at,
        published_at=curation.executed_at,
        rejected_reason=curation.rejected_reason,
        created_at=curation.created_at,
        updated_at=curation.updated_at,
        books=books,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CurationRead)
async def create_curation(data: CurationWrite, staff: AdminStaff, session: Session):
    curation = await svc.create_curation(session, staff.library_id, staff.staff_id, data)
    return await _view(session, staff.library_id, curation)


@router.get("", response_model=list[CurationRead])
async def list_curations(staff: AdminStaff, session: Session, status: ApprovalStatus | None = None):
    rows = await svc.list_curations(session, staff.library_id, status)
    return [await _view(session, staff.library_id, c) for c in rows]


@router.get("/{curation_id}", response_model=CurationRead)
async def get_curation(curation_id: int, staff: AdminStaff, session: Session):
    curation = await svc.get_curation(session, staff.library_id, curation_id)
    return await _view(session, staff.library_id, curation)


@router.patch("/{curation_id}", response_model=CurationRead)
async def update_curation(
    curation_id: int, data: CurationWrite, staff: AdminStaff, session: Session
):
    """초안의 제목·소개·책을 통째로 바꾼다. 초안이 아니면 409."""
    curation = await svc.update_curation(session, staff.library_id, curation_id, data)
    return await _view(session, staff.library_id, curation)


@router.delete("/{curation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_curation(curation_id: int, staff: AdminStaff, session: Session):
    await svc.delete_curation(session, staff.library_id, curation_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{curation_id}/submit", response_model=CurationRead)
async def submit_curation(curation_id: int, staff: AdminStaff, session: Session):
    curation = await svc.submit_curation(session, staff.library_id, curation_id)
    return await _view(session, staff.library_id, curation)


@router.post("/{curation_id}/approve", response_model=CurationRead)
async def approve_curation(curation_id: int, staff: AdminStaff, session: Session):
    """승인하고 바로 게시한다. 승인 대기가 아니면 409."""
    curation = await svc.approve_curation(session, staff.library_id, curation_id, staff.staff_id)
    return await _view(session, staff.library_id, curation)


@router.post("/{curation_id}/reject", response_model=CurationRead)
async def reject_curation(
    curation_id: int, data: RejectRequest, staff: AdminStaff, session: Session
):
    curation = await svc.reject_curation(session, staff.library_id, curation_id, data.reason)
    return await _view(session, staff.library_id, curation)


@router.post("/{curation_id}/unpublish", response_model=CurationRead)
async def unpublish_curation(curation_id: int, staff: AdminStaff, session: Session):
    curation = await svc.unpublish_curation(session, staff.library_id, curation_id)
    return await _view(session, staff.library_id, curation)


@published_router.get("/curations", response_model=list[PublishedCuration])
async def published_curations(staff: CurrentStaff, session: Session):
    """게시된 큐레이션 최신 5개. 지금 추천할 수 있는 책만 담는다."""
    return [
        PublishedCuration(
            id=p.curation.id,
            title=p.curation.title,
            intro=p.curation.intro,
            published_at=p.curation.executed_at,
            books=p.books,
        )
        for p in await svc.published_curations(session, staff.library_id)
    ]
