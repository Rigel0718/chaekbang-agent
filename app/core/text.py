"""글자 정규화 규칙. 가져오기, 검색, 판단 규칙이 같은 규칙을 쓰도록 한 곳에 둔다.

두 가지를 구분한다.

- `clean_spaces`: 저장할 값을 다듬는다. 앞뒤 공백을 없애고 연속 공백을 하나로 줄인다.
- `compact`, `compact_sql`: 비교할 때만 쓴다. 모든 공백을 지우고 소문자로 바꾼다. 저장하지 않는다.
  한국어는 띄어쓰기 표기가 자주 달라서 공백을 지우고 비교한다.

Python의 `\\s`와 PostgreSQL의 `\\s`는 다르다. PostgreSQL은 줄바꿈 없는 공백(U+00A0)을 공백으로 보지
않는다. 그래서 두 쪽 모두 아래의 같은 문자 목록을 쓰고, `tests/core/test_text.py`가 DB에서 비교한다.
대소문자도 PostgreSQL의 `lower`·`ILIKE`와 맞추려고 `casefold`가 아니라 `lower`를 쓴다.

- `jamo`, `jamo_sql`, `jamo_starts`: 찾기와 자동완성의 비교용. 한글 음절을
  호환 자모로 풀어 조합 중인 입력(`데미ㅇ`)과 한 글자 오타(`데미얀`)를 비교할 수 있게 한다.
  겹받침과 이중 모음도 나눈다. 두벌식에서 `ㅘ`는 `ㅗ`, `ㅏ`를 차례로 쳐서 만들기 때문이다.
  된소리(`ㄲ`)는 한 자판이라 둔다. SQL 쪽은 마이그레이션이 만드는 `ko_jamo` 함수이고, 표가 같아야
  한다. 테스트가 DB에서 두 쪽을 비교한다.
"""

import re

from sqlalchemy import ColumnElement, func

JAMO_FUNCTION = "ko_jamo"  # 마이그레이션이 만드는 SQL 함수
JAMO_STARTS_FUNCTION = "ko_jamo_starts"  # 찾기 키 생성 열이 쓰는 SQL 함수

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


# 한글 음절 = 0xAC00 + (초성 * 21 + 중성) * 28 + 종성
_SYLLABLE_BASE = 0xAC00
_SYLLABLE_COUNT = 11172
# fmt: off
CHOSEONG = (
    "ㄱ", "ㄲ", "ㄴ", "ㄷ", "ㄸ", "ㄹ", "ㅁ", "ㅂ", "ㅃ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅉ", "ㅊ", "ㅋ",
    "ㅌ", "ㅍ", "ㅎ",
)
JUNGSEONG = (
    "ㅏ", "ㅐ", "ㅑ", "ㅒ", "ㅓ", "ㅔ", "ㅕ", "ㅖ", "ㅗ", "ㅗㅏ", "ㅗㅐ", "ㅗㅣ", "ㅛ", "ㅜ",
    "ㅜㅓ", "ㅜㅔ", "ㅜㅣ", "ㅠ", "ㅡ", "ㅡㅣ", "ㅣ",
)
JONGSEONG = (
    "", "ㄱ", "ㄲ", "ㄱㅅ", "ㄴ", "ㄴㅈ", "ㄴㅎ", "ㄷ", "ㄹ", "ㄹㄱ", "ㄹㅁ", "ㄹㅂ", "ㄹㅅ",
    "ㄹㅌ", "ㄹㅍ", "ㄹㅎ", "ㅁ", "ㅂ", "ㅂㅅ", "ㅅ", "ㅆ", "ㅇ", "ㅈ", "ㅊ", "ㅋ", "ㅌ", "ㅍ",
    "ㅎ",
)
# 낱자로 들어온 겹자모(조합 중 입력, 붙여 넣은 값)
COMPOUND_JAMO = {
    "ㄳ": "ㄱㅅ", "ㄵ": "ㄴㅈ", "ㄶ": "ㄴㅎ", "ㄺ": "ㄹㄱ", "ㄻ": "ㄹㅁ", "ㄼ": "ㄹㅂ",
    "ㄽ": "ㄹㅅ", "ㄾ": "ㄹㅌ", "ㄿ": "ㄹㅍ", "ㅀ": "ㄹㅎ", "ㅄ": "ㅂㅅ", "ㅘ": "ㅗㅏ",
    "ㅙ": "ㅗㅐ", "ㅚ": "ㅗㅣ", "ㅝ": "ㅜㅓ", "ㅞ": "ㅜㅔ", "ㅟ": "ㅜㅣ", "ㅢ": "ㅡㅣ",
}
# fmt: on


def decompose_jamo(value: str) -> str:
    """한글 음절과 겹자모를 호환 자모로 푼다. 다른 글자는 그대로 둔다. `ko_jamo`와 같다."""
    out: list[str] = []
    for char in value:
        code = ord(char) - _SYLLABLE_BASE
        if 0 <= code < _SYLLABLE_COUNT:
            out.append(CHOSEONG[code // 588] + JUNGSEONG[code % 588 // 28] + JONGSEONG[code % 28])
        else:
            out.append(COMPOUND_JAMO.get(char, char))
    return "".join(out)


def jamo(value: str) -> str:
    """비교용 자모 키: `compact` 뒤 자모로 푼다."""
    return decompose_jamo(compact(value))


def jamo_spaced(value: str) -> str:
    """낱말 앞부분 비교용 자모 키: 공백을 하나로 남기고(`clean_spaces`) 소문자로 바꿔 푼다."""
    return decompose_jamo(clean_spaces(value).lower())


def jamo_sql(expr: ColumnElement) -> ColumnElement:
    """`jamo`와 같은 규칙의 SQL 식. NULL은 빈 문자열로 본다."""
    return getattr(func, JAMO_FUNCTION)(compact_sql(expr))


def jamo_starts(value: str) -> list[str]:
    """낱말 시작 키: 낱말마다 그 낱말부터 끝까지를 공백 없이 이은 자모 키. 첫 값이 `jamo(value)`다.

    `최소한의 한국사` → `[jamo("최소한의한국사"), jamo("한국사")]`. 찾기 키 생성 열의 규칙이고
    SQL 쪽은 `ko_jamo_starts`다.
    """
    spaced = jamo_spaced(value)
    if not spaced:
        return []
    words = spaced.split(" ")
    return ["".join(words[i:]) for i in range(len(words))]


def jamo_starts_sql(expr: ColumnElement) -> ColumnElement:
    """`jamo_starts`와 같은 규칙의 SQL 식. NULL은 NULL이다."""
    return getattr(func, JAMO_STARTS_FUNCTION)(expr)
