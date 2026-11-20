"""연체 안내문 틀의 자리표시: 검사와 채우기. DB와 HTTP를 모르는 순수 함수다.

틀은 LLM이나 관리자가 쓴 문장이고 회원 값은 자리표시로만 들어간다. 채우기는 정해진 다섯 개를
`str.replace`로 바꾼다. `str.format`은 쓰지 않는다. 틀 안의 다른 중괄호나 속성 접근이 코드로
해석되지 않게 하기 위해서다.
"""

import re
from collections.abc import Mapping

NAME = "{이름}"
TITLE = "{서명}"
DUE_DATE = "{반납예정일}"
OVERDUE_DAYS = "{연체일수}"
LIBRARY = "{도서관}"

PLACEHOLDERS = (NAME, TITLE, DUE_DATE, OVERDUE_DAYS, LIBRARY)
REQUIRED = (TITLE, DUE_DATE)

_BRACES = re.compile(r"\{[^{}]*\}")


def check_body(body: str) -> None:
    """모르는 자리표시나 빠진 필수 자리표시가 있으면 ValueError."""
    unknown = sorted({found for found in _BRACES.findall(body) if found not in PLACEHOLDERS})
    if unknown:
        raise ValueError(f"쓸 수 없는 자리표시입니다: {', '.join(unknown)}")
    missing = [p for p in REQUIRED if p not in body]
    if missing:
        raise ValueError(f"꼭 들어가야 하는 자리표시가 없습니다: {', '.join(missing)}")


def fill(body: str, values: Mapping[str, str]) -> str:
    """다섯 자리표시를 값으로 바꾼다. `values`에 없는 자리표시는 그대로 둔다."""
    for placeholder in PLACEHOLDERS:
        if placeholder in values:
            body = body.replace(placeholder, values[placeholder])
    return body
