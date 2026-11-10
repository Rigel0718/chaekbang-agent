"""글자 정규화 규칙. 가져오기, 검색, 판단 규칙이 같은 규칙을 쓰도록 한 곳에 둔다.

두 가지를 구분한다.

- `clean_spaces`: 저장할 값을 다듬는다. 앞뒤 공백을 없애고 연속 공백을 하나로 줄인다.
- `compact`, `compact_sql`: 비교할 때만 쓴다. 모든 공백을 지우고 소문자로 바꾼다. 저장하지 않는다.
  한국어는 띄어쓰기 표기가 자주 달라서 공백을 지우고 비교한다.

Python의 `\\s`와 PostgreSQL의 `\\s`는 다르다. PostgreSQL은 줄바꿈 없는 공백(U+00A0)을 공백으로 보지
않는다. 그래서 두 쪽 모두 아래의 같은 문자 목록을 쓰고, `tests/core/test_text.py`가 DB에서 비교한다.
대소문자도 PostgreSQL의 `lower`·`ILIKE`와 맞추려고 `casefold`가 아니라 `lower`를 쓴다.
"""

import re

from sqlalchemy import ColumnElement, func

# 보이는 공백: 저장할 때는 공백 하나로, 비교할 때는 지운다.
SPACE_CLASS = r"\s "
# 보이지 않는 글자(폭 없는 공백, BOM): 엑셀·웹에서 붙어 온다. 저장할 때도 지운다.
INVISIBLE_CLASS = r"​﻿"
COMPACT_PATTERN = f"[{SPACE_CLASS}{INVISIBLE_CLASS}]"

_SPACES = re.compile(f"[{SPACE_CLASS}]+")
_INVISIBLE = re.compile(f"[{INVISIBLE_CLASS}]")
_COMPACT = re.compile(COMPACT_PATTERN)


def clean_spaces(value: str) -> str:
    """저장용: 보이지 않는 글자를 지우고, 공백을 하나로 줄이고, 앞뒤 공백을 없앤다."""
    return _SPACES.sub(" ", _INVISIBLE.sub("", value)).strip()


def compact(value: str) -> str:
    """비교용: 모든 공백과 보이지 않는 글자를 지우고 소문자로 바꾼다."""
    return _COMPACT.sub("", value).lower()


def compact_sql(expr: ColumnElement) -> ColumnElement:
    """`compact`와 같은 규칙의 SQL 식. NULL은 빈 문자열로 본다."""
    return func.lower(func.regexp_replace(func.coalesce(expr, ""), COMPACT_PATTERN, "", "g"))
