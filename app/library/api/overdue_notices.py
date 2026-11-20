"""연체 안내 API: 안내문 틀 관리와 오늘의 연체 안내 목록. 모두 관리자만, 로직은 service에 있다.

승인은 틀에만 받는다. 승인하면 같은 요청에서 확정하고, 목록은 승인 없이 요청할 때마다 계산한다.
외부 대출 기관은 모든 경로가 409다(service).
"""

from fastapi import APIRouter, Response, status

from app.library.approval import ApprovalStatus
from app.library.deps import AdminStaff, Session
from app.library.models.overdue_notice import OverdueNoticeTemplate
from app.library.schemas.overdue_notice import (
    NoticeList,
    RejectRequest,
    TemplateRead,
    TemplateWrite,
)
from app.library.services import overdue_notices as svc

templates_router = APIRouter(prefix="/overdue-notice-templates", tags=["overdue-notices"])
notices_router = APIRouter(prefix="/overdue-notices", tags=["overdue-notices"])


async def _view(session: Session, library_id: int, template: OverdueNoticeTemplate) -> TemplateRead:
    current = await svc.current_template(session, library_id)
    return _read(template, current.id if current is not None else None)


def _read(template: OverdueNoticeTemplate, current_id: int | None) -> TemplateRead:
    return TemplateRead(
        id=template.id,
        body=template.body,
        status=template.status,
        in_use=template.id == current_id,
        created_by=template.created_by,
        approved_by=template.approved_by,
        approved_at=template.approved_at,
        confirmed_at=template.executed_at,
        rejected_reason=template.rejected_reason,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@templates_router.post("", status_code=status.HTTP_201_CREATED, response_model=TemplateRead)
async def create_template(data: TemplateWrite, staff: AdminStaff, session: Session):
    template = await svc.create_template(session, staff.library_id, staff.staff_id, data)
    return await _view(session, staff.library_id, template)


@templates_router.get("", response_model=list[TemplateRead])
async def list_templates(staff: AdminStaff, session: Session, status: ApprovalStatus | None = None):
    rows = await svc.list_templates(session, staff.library_id, status)
    current = await svc.current_template(session, staff.library_id)
    current_id = current.id if current is not None else None
    return [_read(row, current_id) for row in rows]


@templates_router.get("/{template_id}", response_model=TemplateRead)
async def get_template(template_id: int, staff: AdminStaff, session: Session):
    template = await svc.get_template(session, staff.library_id, template_id)
    return await _view(session, staff.library_id, template)


@templates_router.patch("/{template_id}", response_model=TemplateRead)
async def update_template(
    template_id: int, data: TemplateWrite, staff: AdminStaff, session: Session
):
    """초안의 문장을 바꾼다. 초안이 아니면 409."""
    template = await svc.update_template(session, staff.library_id, template_id, data)
    return await _view(session, staff.library_id, template)


@templates_router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(template_id: int, staff: AdminStaff, session: Session):
    await svc.delete_template(session, staff.library_id, template_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@templates_router.post("/{template_id}/submit", response_model=TemplateRead)
async def submit_template(template_id: int, staff: AdminStaff, session: Session):
    template = await svc.submit_template(session, staff.library_id, template_id)
    return await _view(session, staff.library_id, template)


@templates_router.post("/{template_id}/approve", response_model=TemplateRead)
async def approve_template(template_id: int, staff: AdminStaff, session: Session):
    """승인하고 바로 확정한다. 확정된 틀은 이후 연체 안내 목록이 쓴다. 승인 대기가 아니면 409."""
    template = await svc.approve_template(session, staff.library_id, template_id, staff.staff_id)
    return await _view(session, staff.library_id, template)


@templates_router.post("/{template_id}/reject", response_model=TemplateRead)
async def reject_template(
    template_id: int, data: RejectRequest, staff: AdminStaff, session: Session
):
    template = await svc.reject_template(session, staff.library_id, template_id, data.reason)
    return await _view(session, staff.library_id, template)


@notices_router.get("/today", response_model=NoticeList)
async def notice_list(staff: AdminStaff, session: Session):
    """지금의 연체 대출마다 쓰는 틀로 채운 문안. 요청할 때마다 계산하고 저장하지 않는다."""
    return await svc.notice_list(session, staff.library_id)
