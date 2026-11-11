"""도서관 안내 스키마. 등록 값과 코드가 계산한 값(개관 여부, 반납 예정일)을 함께 돌려준다."""

from datetime import date, time
from enum import StrEnum
from typing import Annotated, Self

from pydantic import BaseModel, Field, model_validator

from app.core.schemas import NonEmpty, ReadModel
from app.library.models.guide import DueOnClosedDay, GuideEntryKind
from app.library.models.library import LoanMode

MAX_ENTRIES = 50
MAX_SPANS_PER_DAY = 4

CONTACT_PHONE_DESCRIPTION = (
    "기관 대표 번호 하나. 담당자·자원봉사자의 개인 휴대폰 번호를 넣지 않는다. "
    "이 번호는 키오스크 화면과 AI 사서의 답에 그대로 나온다."
)
ENTRY_BODY_DESCRIPTION = (
    "이용자에게 그대로 보이는 안내 문장. 개인 연락처나 이름을 넣지 않는다. 500자 이내."
)
HOLIDAY_DESCRIPTION = (
    "대한민국 공휴일(설날·추석·대체공휴일·선거일 포함)에 쉬면 true. 정부가 갑자기 정한 "
    "임시공휴일은 빠질 수 있으니 그날은 임시 휴관일로 등록한다."
)

PhoneText = Annotated[str, Field(min_length=1, max_length=30, pattern=r"^[0-9+()\- ]+$")]


class DayStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    UNKNOWN = "unknown"  # 운영 시간을 등록하지 않아 알 수 없다


class Span(BaseModel):
    opens_at: time
    closes_at: time


class SpanIn(Span):
    weekday: int = Field(ge=0, le=6, strict=True, description="0=월요일 … 6=일요일")


class EntryIn(BaseModel):
    kind: GuideEntryKind
    title: Annotated[NonEmpty, Field(max_length=50)]
    body: Annotated[NonEmpty, Field(max_length=500, description=ENTRY_BODY_DESCRIPTION)]


class GuideUpdate(BaseModel):
    """안내 전체 바꾸기. 보내지 않은 운영 시간과 자유 항목은 지워진다."""

    contact_phone: PhoneText | None = Field(None, description=CONTACT_PHONE_DESCRIPTION)
    loan_limit: Annotated[int, Field(ge=1, strict=True)] | None = Field(
        None, description="한 사람이 빌릴 수 있는 권수. 안내용이며 대출 처리에서 강제하지 않는다"
    )
    closed_on_public_holidays: bool = Field(False, description=HOLIDAY_DESCRIPTION)
    due_on_closed_day: DueOnClosedDay = Field(
        DueOnClosedDay.NEXT_OPEN_DAY,
        description="반납 예정일이 휴관일이면 next_open_day는 다음 개관일로 미루고 keep은 그대로 "
        "둔다",
    )
    hours: list[SpanIn] = Field(
        [], max_length=7 * MAX_SPANS_PER_DAY, description="구간이 없는 요일은 정기 휴관이다"
    )
    entries: list[EntryIn] = Field([], max_length=MAX_ENTRIES)

    @model_validator(mode="after")
    def _check_spans(self) -> Self:
        by_day: dict[int, list[SpanIn]] = {}
        for span in self.hours:
            if span.opens_at >= span.closes_at:
                raise ValueError("여는 시각이 닫는 시각보다 앞이어야 합니다")
            by_day.setdefault(span.weekday, []).append(span)
        for spans in by_day.values():
            spans.sort(key=lambda s: s.opens_at)
            if any(a.closes_at > b.opens_at for a, b in zip(spans, spans[1:], strict=False)):
                raise ValueError("같은 요일의 운영 시간 구간이 겹칩니다")
        return self


class DayHours(BaseModel):
    weekday: int
    weekday_label: str
    spans: list[Span]


class EntryRead(ReadModel):
    kind: GuideEntryKind
    title: str
    body: str


class Due(BaseModel):
    due_on: date
    label: str  # 예: 11월 26일 목요일
    moved_from: date | None = None  # 휴관이라 미루기 전의 날짜
    moved_from_label: str | None = None


class DaySchedule(BaseModel):
    date: date
    label: str
    status: DayStatus
    spans: list[Span]
    closed_reason: str | None
    due_if_borrowed: Due | None  # 개관일에 빌리면 반납 예정일


class Today(DaySchedule):
    now: str  # 기관 시간대의 지금 시각 HH:MM
    open_now: bool | None  # 운영 시간을 모르면 None


class GuideRead(BaseModel):
    registered: bool
    contact_phone: str | None
    loan_limit: int | None
    loan_days: int  # 기관의 기본 대출 기간(읽기 전용, PATCH /library로 고친다)
    loan_mode: LoanMode
    due_is_estimate: bool  # 가져오기 기관은 기존 대출 프로그램이 실제 반납일을 정한다
    closed_on_public_holidays: bool
    due_on_closed_day: DueOnClosedDay
    weekly_hours: list[DayHours]
    entries: list[EntryRead]
    today: Today
    next_days: list[DaySchedule]  # 오늘부터 7일


class ClosureCreate(BaseModel):
    closed_on: date
    reason: Annotated[str, Field(max_length=100)] | None = None


class ClosureRead(ReadModel):
    id: int
    closed_on: date
    reason: str | None
