"""기관 시간대 기준의 오늘과 지금. 테스트는 이 모듈의 함수를 바꿔 끼워 날짜를 정한다.

service는 `from app.core import clock` 후 `clock.today()`로 불러야 바꿔 끼운 값이 적용된다.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def now() -> datetime:
    return datetime.now(UTC)


def today() -> date:
    return datetime.now(ZoneInfo(get_settings().library_timezone)).date()
