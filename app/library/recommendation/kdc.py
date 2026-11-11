"""청구기호의 KDC 주류 이름. "813이 무슨 뜻이에요?"를 LLM 기억에 맡기지 않는다.

청구기호가 세 자리 숫자로 시작할 때만 정한다. 별치기호가 앞에 붙은 `아 813`, `J 813`은 기관마다
규칙이 달라 비운다. 강목(100개)은 이번 질문에 필요 없어 주류 10개만 둔다.
"""

import re

KDC_MAIN_CLASSES = (
    "총류",
    "철학",
    "종교",
    "사회과학",
    "자연과학",
    "기술과학",
    "예술",
    "언어",
    "문학",
    "역사",
)
_LEADING_CLASS = re.compile(r"^\s*(\d)\d{2}(?!\d)")


def kdc_class_name(call_number: str | None) -> str | None:
    if not call_number:
        return None
    match = _LEADING_CLASS.match(call_number)
    return KDC_MAIN_CLASSES[int(match.group(1))] if match else None
