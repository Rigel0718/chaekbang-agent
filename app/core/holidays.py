"""대한민국 공휴일 판정. 기관을 모르는 결정적 규칙이다.

`holidays` 패키지로 오프라인에서 계산한다(음력 명절, 대체공휴일, 선거일 포함). 외부 호출과 키가
없다. 정부가 갑자기 정하는 임시공휴일은 패키지를 갱신하기 전까지 빠진다. 그날은 기관이 임시 휴관으로
등록한다. 출처를 바꾸면(예: 공공데이터 특일 정보 API) 이 함수만 바꾼다.
"""

from datetime import date
from functools import lru_cache

import holidays


@lru_cache(maxsize=16)
def _year(year: int) -> dict[date, str]:
    return dict(holidays.KR(language="ko", years=year).items())


def public_holiday(day: date) -> str | None:
    """그날이 공휴일이면 이름(예: `추석`), 아니면 None."""
    return _year(day.year).get(day)
