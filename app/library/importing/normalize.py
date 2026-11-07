"""셀 값 정규화. 결정적인 코드로 처리하고 LLM에 맡기지 않는다."""

import re
from datetime import date, datetime
from typing import Any

from app.core.isbn import InvalidIsbnError, isbn10_to_13, normalize_isbn
from app.library.models.catalog import AcquisitionType, HoldingStatus

_SPACES = re.compile(r"\s+")
_NON_DIGIT = re.compile(r"[^\d]")
_DATE = re.compile(r"^(\d{4})[-./년\s]*(\d{1,2})[-./월\s]*(\d{1,2})일?$")

STATUS_LABELS: dict[str, HoldingStatus] = {
    "대출가능": HoldingStatus.AVAILABLE,
    "비치": HoldingStatus.AVAILABLE,
    "비치중": HoldingStatus.AVAILABLE,
    "정상": HoldingStatus.AVAILABLE,
    "소장": HoldingStatus.AVAILABLE,
    "소장중": HoldingStatus.AVAILABLE,
    "대출중": HoldingStatus.ON_LOAN,
    "대출": HoldingStatus.ON_LOAN,
    "대출됨": HoldingStatus.ON_LOAN,
    "분실": HoldingStatus.LOST,
    "망실": HoldingStatus.LOST,
    "훼손": HoldingStatus.DAMAGED,
    "파손": HoldingStatus.DAMAGED,
    "제적": HoldingStatus.WITHDRAWN,
    "폐기": HoldingStatus.WITHDRAWN,
}

ACQUISITION_LABELS: dict[str, AcquisitionType] = {
    "구입": AcquisitionType.PURCHASED,
    "구매": AcquisitionType.PURCHASED,
    "매입": AcquisitionType.PURCHASED,
    "납품": AcquisitionType.PURCHASED,
    "구입도서": AcquisitionType.PURCHASED,
    "기증": AcquisitionType.DONATED,
    "수증": AcquisitionType.DONATED,
    "기증도서": AcquisitionType.DONATED,
}


def clean_text(value: Any) -> str | None:
    """앞뒤 공백을 없애고 연속 공백을 하나로 줄인다. 빈 값은 None. 엑셀 숫자 셀은 정수로 적는다."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    text = _SPACES.sub(" ", str(value)).strip()
    return text or None


def normalize_cell_isbn(value: Any) -> tuple[str | None, bool]:
    """(13자리 ISBN 또는 None, 값이 있는데 잘못됐는지)."""
    text = clean_text(value)
    if text is None:
        return None, False
    if text.endswith(".0"):
        text = text[:-2]
    compact = re.sub(r"[\s\-]", "", text)
    try:
        if len(compact) == 10:
            return isbn10_to_13(compact), False
        return normalize_isbn(compact), False
    except InvalidIsbnError:
        return None, True


def parse_price(value: Any) -> int | None:
    """'15,000원', 15000, 15000.0 → 15000. 정수로 읽을 수 없으면 None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float):
        return int(value) if value.is_integer() and value >= 0 else None
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    if "." in text or text.startswith("-"):
        return None
    digits = _NON_DIGIT.sub("", text)
    return int(digits) if digits else None


def parse_date(value: Any) -> date | None:
    """연·월·일이 모두 있을 때만 날짜로 읽는다. 연도만 있으면 지어내지 않고 None."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = clean_text(value)
    if text is None:
        return None
    if re.fullmatch(r"\d{8}", text):
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    match = _DATE.match(text)
    if match is None:
        return None
    try:
        return date(int(match[1]), int(match[2]), int(match[3]))
    except ValueError:
        return None


def _label_key(value: str) -> str:
    return _SPACES.sub("", value)


def parse_status(value: str | None) -> tuple[HoldingStatus | None, bool]:
    """(사본 상태 또는 None, 값이 있는데 모르는 표기인지)."""
    if value is None:
        return None, False
    status = STATUS_LABELS.get(_label_key(value))
    return status, status is None


def parse_acquisition(value: str | None) -> AcquisitionType | None:
    if value is None:
        return None
    return ACQUISITION_LABELS.get(_label_key(value))
