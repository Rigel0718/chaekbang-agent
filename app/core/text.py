"""글자 정규화 규칙. 가져오기, 검색, 판단 규칙, 저자 해석이 같은 규칙을 쓰도록 한 곳에 둔다.

세 단계를 구분한다.

- 저장용 `clean_spaces`: 보여 줄 값을 다듬는다. 유니코드 NFC로 맞추고, 보이지 않는 글자를 지우고,
  공백을 하나로 줄이고, 앞뒤 공백을 없앤다. 대소문자, 문장부호, 전각 글자는 그대로 둔다.
- 비교용 `compact`, `compact_sql`: 맞춰 볼 때만 쓴다. NFC로 맞추고, 전각 영문·숫자·기호를 반각으로
  바꾸고, 모든 공백을 지우고, 소문자로 바꾼다. 저장하지 않는다. 한국어는 띄어쓰기 표기가 자주 달라서
  공백을 지우고 비교한다.
- 이름 맞춤 `match_key`: 사람·단체 이름과 시리즈명을 맞출 때 쓴다. 비교용에서 글자·숫자가 아닌 것을
  모두 지운다(`J.K. Rowling` → `jkrowling`). 코드가 계산해 저장하므로 SQL 쪽 규칙은 없다.
  서명 찾기에는 쓰지 않는다. 서명에서는 문장부호가 뜻을 가른다(`C++`, `3.1 운동`).

NFKC는 쓰지 않는다. 한글 호환 자모(`ㄱ` U+3131)를 조합형 자모로 바꿔 자모 키(`데미ㅇ`)가 깨진다.
전각은 U+FF01~U+FF5E를 U+0021~U+007E로 옮기는 표 하나로 바꾼다(전각 공백은 공백 목록에 있다).

Python의 `\\s`와 PostgreSQL의 `\\s`는 다르다. PostgreSQL은 줄바꿈 없는 공백(U+00A0)을 공백으로 보지
않는다. 그래서 두 쪽 모두 아래의 같은 문자 목록을 쓰고, `tests/core/test_text.py`가 DB에서 비교한다.
대소문자도 PostgreSQL의 `lower`·`ILIKE`와 맞추려고 `casefold`가 아니라 `lower`를 쓴다.

- `strip_edition`: 찾기용으로 서명의 판본·묶음 표기(`(완전판)`, `[예스리커버]`, `+ 엽서 3종`)를
  지운다. 이용자는 이 표기를 말하지 않는다. 저장하지 않고 화면의 서명도 바꾸지 않는다.
- `jamo`, `jamo_sql`, `jamo_starts`: 찾기와 자동완성의 비교용. 한글 음절을
  호환 자모로 풀어 조합 중인 입력(`데미ㅇ`)과 한 글자 오타(`데미얀`)를 비교할 수 있게 한다.
  겹받침과 이중 모음도 나눈다. 두벌식에서 `ㅘ`는 `ㅗ`, `ㅏ`를 차례로 쳐서 만들기 때문이다.
  된소리(`ㄲ`)는 한 자판이라 둔다. SQL 쪽은 마이그레이션이 만드는 `ko_jamo`, `ko_jamo_starts`
  함수이고, 표가 같아야 한다. 테스트가 DB에서 두 쪽을 비교한다.
- `kdc_key`: 분류기호 표기를 KDC 숫자 문자열(`813.7`)로 맞춘다.
- `korean_order`: 서명 정렬 순서(가나다). 기호·공백, 숫자, 한글, 영문 순서이고 영문은 대소문자를
  가리지 않는다(같으면 소문자 먼저). 숫자는 글자 순서다(`가나다 10` < `가나다 2`). DB 기본 collation
  (`en_US.utf8`)은 한글이 가나다순이 아니어서, 정렬할 때만 ICU `ko-x-icu`를 건다. ORDER BY 키에만
  쓰고 비교·검색(`=`, `LIKE`, 자모 키, 유사도)에는 쓰지 않는다. collation이 있는지는 마이그레이션이
  본다.
"""

import re
import unicodedata

from sqlalchemy import ColumnElement, func, literal_column

JAMO_FUNCTION = "ko_jamo"  # 마이그레이션이 만드는 SQL 함수
JAMO_STARTS_FUNCTION = "ko_jamo_starts"  # 찾기 키 생성 열이 쓰는 SQL 함수
KOREAN_COLLATION = "ko-x-icu"  # 서명 정렬 순서. PostgreSQL ICU collation

# 보이는 공백: 저장할 때는 공백 하나로, 비교할 때는 지운다.
SPACE_CLASS = r"\s "
# 보이지 않는 글자(폭 없는 공백, BOM): 엑셀·웹에서 붙어 온다. 저장할 때도 지운다.
INVISIBLE_CLASS = r"​﻿"
COMPACT_PATTERN = f"[{SPACE_CLASS}{INVISIBLE_CLASS}]"

# 전각 영문·숫자·기호(U+FF01~U+FF5E)와 같은 자리의 반각(U+0021~U+007E). SQL `translate`도 쓴다.
FULLWIDTH = "".join(chr(code) for code in range(0xFF01, 0xFF5F))
HALFWIDTH = "".join(chr(code) for code in range(0x21, 0x7F))
_TO_HALFWIDTH = str.maketrans(FULLWIDTH, HALFWIDTH)

_SPACES = re.compile(f"[{SPACE_CLASS}]+")
_INVISIBLE = re.compile(f"[{INVISIBLE_CLASS}]")
_COMPACT = re.compile(COMPACT_PATTERN)


def nfc(value: str) -> str:
    return unicodedata.normalize("NFC", value)


def halfwidth(value: str) -> str:
    """전각 영문·숫자·기호를 반각으로 바꾼다. 다른 글자는 그대로 둔다."""
    return value.translate(_TO_HALFWIDTH)


def clean_spaces(value: str) -> str:
    """저장용: NFC로 맞추고, 보이지 않는 글자를 지우고, 공백을 하나로 줄이고, 앞뒤 공백을 없앤다."""
    return _SPACES.sub(" ", _INVISIBLE.sub("", nfc(value))).strip()


def compact(value: str) -> str:
    """비교용: NFC, 전각 → 반각, 모든 공백과 보이지 않는 글자 제거, 소문자."""
    return _COMPACT.sub("", halfwidth(nfc(value))).lower()


def _nfc_halfwidth_sql(expr: ColumnElement) -> ColumnElement:
    return func.translate(func.normalize(expr, literal_column("NFC")), FULLWIDTH, HALFWIDTH)


def compact_sql(expr: ColumnElement) -> ColumnElement:
    """`compact`와 같은 규칙의 SQL 식. NULL은 빈 문자열로 본다."""
    cleaned = _nfc_halfwidth_sql(func.coalesce(expr, ""))
    return func.lower(func.regexp_replace(cleaned, COMPACT_PATTERN, "", "g"))


def korean_order(expr: ColumnElement) -> ColumnElement:
    """서명 정렬 순서(가나다)의 정렬 키. ORDER BY에만 쓴다. 비교·검색에는 쓰지 않는다."""
    return expr.collate(KOREAN_COLLATION)


# 이름 맞춤 키에서 남기는 것: 유니코드 글자(L*)와 숫자(N*). 나머지(문장부호, 기호, 공백)는 지운다.
def match_key(value: str) -> str:
    """이름 맞춤 키: 비교용 키에서 글자·숫자가 아닌 것을 지운다. `김 영 하` → `김영하`."""
    return "".join(c for c in compact(value) if unicodedata.category(c)[0] in "LN")


_KDC = re.compile(r"(\d{3})(?:\.(\d+))?\.?(?!\d)")


def kdc_key(value: str | None) -> str | None:
    """KDC 숫자 문자열. 세 자리 숫자로 시작하지 않으면 None이다.

    전각 숫자, 공백, 대소문자, 앞의 `KDC`, 뒤의 저자기호(`813.7-한232ㅊ`)는 무시한다.
    별치기호가 앞에 붙은 값(`아 813`)은 기관마다 규칙이 달라 읽지 않는다.
    """
    if not value:
        return None
    key = compact(value)
    if key.startswith("kdc"):
        key = key[3:].lstrip(":")
    match = _KDC.match(key)
    if match is None:
        return None
    main, fraction = match.groups()
    return f"{main}.{fraction}" if fraction else main


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
    """낱말 앞부분 비교용 자모 키: 공백을 하나로 남기고(`clean_spaces`) 반각·소문자로 바꿔 푼다."""
    return decompose_jamo(halfwidth(clean_spaces(value)).lower())


def jamo_sql(expr: ColumnElement) -> ColumnElement:
    """`jamo`와 같은 규칙의 SQL 식. NULL은 빈 문자열로 본다."""
    return getattr(func, JAMO_FUNCTION)(compact_sql(expr))


# 판본·묶음 표기: 닫힌 대괄호·괄호(모두), 남은 여는 괄호부터 끝까지, 공백을 둔 `+` 뒤.
# 공백은 `clean_spaces`로 하나로 줄인 뒤라 보통 공백만 본다. SQL 쪽은 PostgreSQL 정규식 문법이다.
EDITION_PATTERNS = (r"\[[^\]]*\]", r"\([^)]*\)", r"[(\[].*$", r" \+ .*$")
EDITION_SQL_PATTERNS = (r"\[[^]]*\]", r"\([^)]*\)", r"[(\[].*$", r" \+ .*$")
_EDITION = tuple(re.compile(pattern) for pattern in EDITION_PATTERNS)


def strip_edition(value: str) -> str:
    """판본·묶음 표기를 지운 서명(`clean_spaces` 적용). 지워서 비면 원래 서명이다. `C++`는 둔다."""
    cleaned = clean_spaces(value)
    stripped = cleaned
    for pattern in _EDITION:
        stripped = pattern.sub(" ", stripped)
    return clean_spaces(stripped) or cleaned


def jamo_starts(value: str) -> list[str]:
    """낱말 시작 키: 낱말마다 그 낱말부터 끝까지를 공백 없이 이은 자모 키.

    판본·묶음 표기를 지운 서명으로 만든다(`strip_edition`). 첫 값은 `jamo(strip_edition(value))`다.
    `최소한의 한국사 (개정판)` → `[jamo("최소한의한국사"), jamo("한국사")]`. 찾기 키 생성 열의
    규칙이고 SQL 쪽은 `ko_jamo_starts`다.
    """
    spaced = jamo_spaced(strip_edition(value))
    if not spaced:
        return []
    words = spaced.split(" ")
    return ["".join(words[i:]) for i in range(len(words))]


def jamo_starts_sql(expr: ColumnElement) -> ColumnElement:
    """`jamo_starts`와 같은 규칙의 SQL 식. NULL은 NULL이다."""
    return getattr(func, JAMO_STARTS_FUNCTION)(expr)


_RIEUL = 8  # 종성 ㄹ의 번호(JONGSEONG)
_PARTICLES = {"을/를", "이/가", "은/는", "과/와", "으로/로"}


def with_particle(word: str, pair: str) -> str:
    """앞말의 받침을 보고 조사를 붙인다.

    `pair`는 "받침 있을 때/없을 때"다(을/를, 이/가, 은/는, 과/와, 으로/로).

    화면에 나오는 문구에 "을(를)" 같은 겸용 조사를 쓰지 않으려고 둔다. "으로/로"는 받침이 ㄹ이어도
    "로"다(`휴관일로`). 마지막 글자가 한글 음절이 아니면 받침 없는 쪽을 쓴다.
    """
    if pair not in _PARTICLES:
        raise ValueError(f"모르는 조사: {pair}")
    with_final, without_final = pair.split("/")
    code = ord(word[-1]) - _SYLLABLE_BASE if word else -1
    final = code % 28 if 0 <= code < _SYLLABLE_COUNT else 0
    if pair == "으로/로" and final == _RIEUL:
        final = 0
    return word + (with_final if final else without_final)
