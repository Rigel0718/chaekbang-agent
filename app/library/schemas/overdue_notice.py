"""연체 안내문 틀과 연체 안내 목록의 요청·응답 스키마. 기관 값은 받지 않는다(토큰으로 정한다)."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.library.approval import ApprovalStatus
from app.library.models.overdue_notice import BODY_LIMIT
from app.library.overdue_template import check_body
from app.library.schemas.curation import RejectRequest

__all__ = [
    "NoticeLine",
    "NoticeList",
    "OverdueLoanItem",
    "OverdueLoanList",
    "RejectRequest",
    "TemplateRead",
    "TemplateWrite",
]


class TemplateWrite(BaseModel):
    """만들기와 고치기(통째로 바꿈)의 본문. 개인정보 형태 검사는 DB가 필요해 service가 한다."""

    model_config = ConfigDict(extra="forbid")

    body: str = Field(min_length=1, max_length=BODY_LIMIT)

    @field_validator("body")
    @classmethod
    def _placeholders(cls, value: str) -> str:
        check_body(value)
        return value


class TemplateRead(BaseModel):
    id: int
    body: str
    status: ApprovalStatus
    in_use: bool  # 지금 연체 안내 목록이 쓰는 틀인지
    created_by: int | None
    approved_by: int | None
    approved_at: datetime | None
    confirmed_at: datetime | None
    rejected_reason: str | None
    created_at: datetime
    updated_at: datetime


class NoticeLine(BaseModel):
    """연체 대출 한 건. 회원 값은 이 관리자용 목록에만 있다."""

    member_number: str
    name: str
    phone: str | None
    title: str
    accession_number: str
    due_on: date
    overdue_days: int
    message: str


class NoticeList(BaseModel):
    today: date
    template_id: int
    total: int
    lines: list[NoticeLine]


class OverdueLoanItem(BaseModel):
    """운영 에이전트에 보내는 연체 한 건. 회원 값은 넣지 않는다(허용 목록 테스트가 고정한다)."""

    title: str
    accession_number: str
    due_on: date
    overdue_days: int


class OverdueLoanList(BaseModel):
    total: int
    shown: int
    truncated: bool
    has_template: bool  # 확정된 안내문 틀이 있는지
    items: list[OverdueLoanItem]
