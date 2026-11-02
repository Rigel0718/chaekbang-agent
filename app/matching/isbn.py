"""ISBN 정규화와 ISBN-13 검증. 결정적인 코드로 처리하고 LLM에 맡기지 않는다."""

import re

_SEPARATORS = re.compile(r"[\s\-]")


class InvalidIsbnError(ValueError):
    pass


def normalize_isbn(raw: str) -> str:
    """하이픈·공백을 없앤 13자리 ISBN을 돌려준다. 형식이나 체크 디지트가 틀리면 InvalidIsbnError."""
    isbn = _SEPARATORS.sub("", raw)
    if len(isbn) != 13 or not isbn.isdigit():
        raise InvalidIsbnError(f"ISBN은 13자리 숫자여야 합니다: {raw!r}")
    if isbn13_check_digit(isbn[:12]) != isbn[12]:
        raise InvalidIsbnError(f"ISBN 체크 디지트가 올바르지 않습니다: {raw!r}")
    return isbn


def isbn13_check_digit(first12: str) -> str:
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(first12))
    return str((10 - total % 10) % 10)
