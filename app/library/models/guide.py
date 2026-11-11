"""도서관 안내: 대표 연락처와 이용 규칙, 요일별 운영 시간, 임시 휴관일, 자유 항목.

모두 기관 데이터다. 계산에 쓰는 값(운영 시간, 휴관일, 반납일 규칙)은 칸으로 나누고, 말로만 전하는
값(시설 위치, 이용 규칙, 알림)은 자유 항목으로 둔다. 정기 휴관은 저장하지 않는다. 운영 시간 구간이
없는 요일이 정기 휴관이다. `library_guides` 행이 없으면 안내를 등록하지 않은 기관이다.
"""

from datetime import date, time
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.model_base import Base, TimestampMixin, str_enum


class DueOnClosedDay(StrEnum):
    NEXT_OPEN_DAY = "next_open_day"  # 반납 예정일이 휴관이면 다음 개관일로 미룬다
    KEEP = "keep"  # 그대로 둔다(무인 반납함이 있는 기관)


class GuideEntryKind(StrEnum):
    FACILITY = "facility"  # 시설 위치
    RULE = "rule"  # 이용 규칙
    NOTICE = "notice"  # 알림


class LibraryGuide(TimestampMixin, Base):
    __tablename__ = "library_guides"
    __table_args__ = (CheckConstraint("loan_limit >= 1", name="loan_limit_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(
        ForeignKey("libraries.id", ondelete="RESTRICT"), unique=True
    )
    # 기관 대표 번호만 둔다. 담당자·자원봉사자 개인 번호를 넣지 않는다
    contact_phone: Mapped[str | None] = mapped_column(String(30))
    loan_limit: Mapped[int | None] = mapped_column(Integer)
    closed_on_public_holidays: Mapped[bool] = mapped_column(server_default="false")
    due_on_closed_day: Mapped[DueOnClosedDay] = mapped_column(
        str_enum(DueOnClosedDay, "due_on_closed_day"), server_default=DueOnClosedDay.NEXT_OPEN_DAY
    )


class OpeningHours(Base):
    __tablename__ = "library_opening_hours"
    __table_args__ = (
        CheckConstraint("weekday BETWEEN 0 AND 6", name="weekday_range"),
        CheckConstraint("opens_at < closes_at", name="opens_before_closes"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(
        ForeignKey("libraries.id", ondelete="RESTRICT"), index=True
    )
    weekday: Mapped[int] = mapped_column(SmallInteger)  # 0=월요일 … 6=일요일
    opens_at: Mapped[time] = mapped_column(Time)
    closes_at: Mapped[time] = mapped_column(Time)


class LibraryClosure(TimestampMixin, Base):
    __tablename__ = "library_closures"
    __table_args__ = (UniqueConstraint("library_id", "closed_on"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    closed_on: Mapped[date] = mapped_column(Date)
    reason: Mapped[str | None] = mapped_column(String(100))


class GuideEntry(Base):
    __tablename__ = "library_guide_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(
        ForeignKey("libraries.id", ondelete="RESTRICT"), index=True
    )
    kind: Mapped[GuideEntryKind] = mapped_column(str_enum(GuideEntryKind, "guide_entry_kind"))
    title: Mapped[str] = mapped_column(String(50))
    body: Mapped[str] = mapped_column(Text)
    position: Mapped[int] = mapped_column(SmallInteger)
