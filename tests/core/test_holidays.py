"""공휴일 판정. library/library-guide의 '개관 여부 판정'이 쓰는 규칙이다."""

from datetime import date

import pytest

from app.core.holidays import public_holiday


@pytest.mark.parametrize(
    ("day", "name"),
    [
        (date(2026, 2, 17), "설날"),
        (date(2026, 2, 18), "설날 다음날"),
        (date(2026, 9, 25), "추석"),
        (date(2026, 3, 2), "삼일절 대체 휴일"),
        (date(2026, 6, 3), "지방선거일"),
        (date(2027, 2, 9), "설날 대체 휴일"),
        (date(2027, 9, 15), "추석"),
        (date(2027, 10, 11), "한글날 대체 휴일"),
    ],
)
def test_public_holidays(day: date, name: str) -> None:
    assert public_holiday(day) == name


def test_weekday_is_not_holiday() -> None:
    assert public_holiday(date(2026, 11, 11)) is None
