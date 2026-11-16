"""외부 응답 값을 읽는 공통 규칙. 출처마다의 해석(`parsing.py`)이 함께 쓴다.

필드마다 관대하게 읽는다. 읽을 수 없는 값은 그 필드만 비운다.
"""

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

MAX_PRICE = 2**31 - 1  # 정가 열(Integer)의 상한

_DATE = re.compile(r"(\d{4})-?(\d{2})-?(\d{2})(?:[T ].*)?")


def clean(value: Any) -> str | None:
    """빈 문자열은 값 없음이다. 앞뒤 공백을 지우고 줄바꿈은 \\n으로 통일한다."""
    if not isinstance(value, str):
        return None
    return value.replace("\r\n", "\n").replace("\r", "\n").strip() or None


def fit(value: str | None, limit: int | None) -> str | None:
    """저장 길이를 넘는 값은 비운다."""
    return None if value is not None and limit is not None and len(value) > limit else value


def parse_date(value: Any) -> date | None:
    """YYYYMMDD, YYYY-MM-DD, ISO 8601 날짜·시각을 읽는다. 해만 있는 값은 날짜가 아니다."""
    text = clean(value)
    match = _DATE.fullmatch(text) if text else None
    if match is None:
        return None
    try:
        return datetime.strptime("".join(match.groups()), "%Y%m%d").date()
    except ValueError:
        return None


def parse_price(value: Any) -> int | None:
    """decimal로 오는 정가를 원 단위 정수로 바꾼다. float를 거치지 않는다."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        price = Decimal(str(value))
    except InvalidOperation:
        return None
    if not price.is_finite() or price != price.to_integral_value() or not 0 <= price <= MAX_PRICE:
        return None
    return int(price)
