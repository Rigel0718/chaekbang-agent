"""분석 기간. LLM은 프리셋이나 월 숫자만 고르고 날짜는 코드가 계산한다.

LLM은 오늘이 며칠인지 모른다(프롬프트에 날짜를 넣지 않는다). 그래서 "지난달"을 날짜로 바꾸는 일을
맡기지 않는다. 월 숫자는 미래가 아닌 가장 최근의 그 달이다(오늘이 11월이면 12는 작년 12월).
기간은 양 끝을 포함하고, 끝일은 오늘을 넘지 않는다.
"""

import calendar
from datetime import date, timedelta
from enum import StrEnum

from pydantic import BaseModel

from app.core.errors import InvalidRequestError


class PeriodPreset(StrEnum):
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    LAST_30_DAYS = "last_30_days"
    LAST_90_DAYS = "last_90_days"
    THIS_YEAR = "this_year"
    LAST_YEAR = "last_year"
    LAST_365_DAYS = "last_365_days"


class PeriodError(InvalidRequestError):
    """기간 입력이 규칙에 맞지 않는다. tool에서는 LLM에 오류로 돌아간다."""


class Period(BaseModel):
    start: date
    end: date
    label: str  # 코드가 만든 한국어 표기. 답에 그대로 쓴다
    in_progress: bool  # 끝일이 오늘이면 아직 진행 중인 기간


def _month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _last_days(today: date, days: int) -> tuple[date, date]:
    return today - timedelta(days=days - 1), today


def _preset_range(preset: PeriodPreset, today: date) -> tuple[date, date]:
    match preset:
        case PeriodPreset.THIS_MONTH:
            return today.replace(day=1), today
        case PeriodPreset.LAST_MONTH:
            last = today.replace(day=1) - timedelta(days=1)
            return last.replace(day=1), last
        case PeriodPreset.LAST_30_DAYS:
            return _last_days(today, 30)
        case PeriodPreset.LAST_90_DAYS:
            return _last_days(today, 90)
        case PeriodPreset.THIS_YEAR:
            return date(today.year, 1, 1), today
        case PeriodPreset.LAST_YEAR:
            return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
        case PeriodPreset.LAST_365_DAYS:
            return _last_days(today, 365)


def _month_range(month: int, today: date) -> tuple[date, date]:
    if not 1 <= month <= 12:
        raise PeriodError("월은 1~12입니다")
    year = today.year if month <= today.month else today.year - 1
    return date(year, month, 1), min(_month_end(year, month), today)


def _label(start: date, end: date) -> str:
    if start.year == end.year and start.month == end.month:
        if start.day == end.day:
            return f"{start.year}년 {start.month}월 {start.day}일"
        return f"{start.year}년 {start.month}월 {start.day}일~{end.day}일"
    if start.year == end.year:
        return f"{start.year}년 {start.month}월 {start.day}일~{end.month}월 {end.day}일"
    return f"{start.year}년 {start.month}월 {start.day}일~{end.year}년 {end.month}월 {end.day}일"


def resolve_period(preset: PeriodPreset | None, month: int | None, today: date) -> Period:
    """프리셋과 월 중 정확히 하나로 기간을 계산한다."""
    if (preset is None) == (month is None):
        raise PeriodError("period와 month 중 하나만 주세요")
    start, end = _preset_range(preset, today) if preset is not None else _month_range(month, today)
    return Period(start=start, end=end, label=_label(start, end), in_progress=end == today)
