"""어린이 도서 판단 규칙. 어린이 도서는 영유아·초등학생 대상 도서다.

판단은 표 기반 코드로 하고, 불확실하면 근거 없음으로 둔다. 분류 원문은 값이 카테고리 이름과
항상 같지는 않아서 정확히 일치하는 값만 본다.
"""

import re
from collections.abc import Sequence

from app.core.text import compact

CHILDREN_CATEGORIES = frozenset({"국내도서-유아", "국내도서-어린이", "국내도서-초등학습서"})
CHILDREN_MARKS = {"아", "아동", "어린이", "유", "유아", "j"}
CHILDREN_SHELF_WORDS = ("어린이", "아동", "유아")
CHILDREN_ADDITION_DIGITS = ("6", "7")  # 독자대상기호: 초등 학습참고서, 아동


def has_children_label(
    separate_mark: str | None, shelf_location: str | None, addition_code: str | None
) -> bool:
    """별치기호(완전 일치), 자료실 이름, 부가기호 첫 자리 중 하나라도 아동이면 True."""
    if separate_mark and compact(separate_mark) in CHILDREN_MARKS:
        return True
    if shelf_location and any(word in shelf_location for word in CHILDREN_SHELF_WORDS):
        return True
    code = (addition_code or "").strip()
    return len(code) == 5 and code.isdigit() and code[0] in CHILDREN_ADDITION_DIGITS


def is_children_category(category: str | None) -> bool:
    return category in CHILDREN_CATEGORIES


# --- 어린이 요청 판단 ---
#
# 이용자 문장을 순서대로 보고 상태를 바꾼다. 애매하면 어린이 쪽으로 간다.
# 일반 도서가 어린이에게 가는 쪽이 어른 요청이 어린이 도서로 좁혀지는 쪽보다 큰 실수이기 때문이다.
#
# | 문장 | 상태 |
# | --- | --- |
# | 13세 이하 나이 | 어린이 요청 |
# | 14세 이상, 청소년·대학, 부모가 읽을 표현 | 근거로 보지 않음. 어른 표현이 있으면 해제 |
# | 어린이 표현 | 어린이 요청 |
# | 어른 표현만 있음 | 해제 |
# | 그 밖 | 앞 상태 유지 |

CHILDREN_AGE_LIMIT = 13

_KOREAN_AGES = {
    "열아홉": 19,
    "열여덟": 18,
    "열일곱": 17,
    "열여섯": 16,
    "열다섯": 15,
    "열네": 14,
    "열세": 13,
    "열두": 12,
    "열한": 11,
    "스무": 20,
    "스물": 20,
    "서른": 30,
    "마흔": 40,
    "쉰": 50,
    "여덟": 8,
    "아홉": 9,
    "다섯": 5,
    "여섯": 6,
    "일곱": 7,
    "열": 10,
    "한": 1,
    "두": 2,
    "세": 3,
    "네": 4,
}
_DIGIT_AGE = re.compile(r"(\d{1,3})\s*(?:살|세(?![트대기상계])|개월)")
_MONTHS = re.compile(r"\d{1,2}\s*개월")
_KOREAN_AGE = re.compile(
    r"(?<![가-힣])(" + "|".join(sorted(_KOREAN_AGES, key=len, reverse=True)) + r")\s*살"
)
# 어린이 표현. 비슷한 낱말(아이디어, 아이돌, 딸기, 아들러 등)은 뒤 글자로 뺀다.
_CHILD_WORDS = re.compile(
    r"아이(?!디어|돌|스|폰|패드|템|콘|유|언|큐|비|러브|쇼핑|맥|들러)"
    r"|아기|애기|어린이|아동|영유아|유아|초등|유치원|어린이집|그림책|동화|손주|손자|손녀"
    r"|아들(?!러)|딸(?!기)|꼬마|키즈|우리\s*애|애들|[1-6]\s*학년|초\s*[1-6](?!\d)"
)
_TEEN_WORDS = re.compile(r"청소년|중학|고등|고교|대학|중\s*[1-3](?!\d)|고\s*[1-3](?!\d)|수능")
_PARENT_WORDS = re.compile(
    r"훈육|육아|양육|자녀\s*교육|부모\s*교육|부모가\s*읽|엄마가\s*읽|아빠가\s*읽|부모용|교사용"
)
_ADULT_WORDS = re.compile(
    r"(?:제가|내가|저|나|본인|혼자)\s*(?:가\s*)?(?:읽|볼)|어른|성인|직장인|퇴근|어르신|부모님"
)


def _ages(text: str) -> list[int]:
    ages = [int(m.group(1)) for m in _DIGIT_AGE.finditer(text)]
    if _MONTHS.search(text):
        ages.append(0)
    ages += [_KOREAN_AGES[m.group(1)] for m in _KOREAN_AGE.finditer(text)]
    return ages


def classify_request(text: str) -> bool | None:
    """한 문장의 판단. True는 어린이 요청, False는 해제, None은 앞 상태 유지다."""
    ages = _ages(text)
    adult = _ADULT_WORDS.search(text) is not None
    if any(age <= CHILDREN_AGE_LIMIT for age in ages):
        return True
    if ages or _TEEN_WORDS.search(text) or _PARENT_WORDS.search(text):
        return False if adult else None
    if _CHILD_WORDS.search(text):
        return True
    if adult:
        return False
    return None


def is_children_request(user_texts: Sequence[str]) -> bool:
    """대화의 이용자 문장을 순서대로 보고 마지막 상태를 돌려준다."""
    state = False
    for text in user_texts:
        decided = classify_request(text)
        if decided is not None:
            state = decided
    return state
