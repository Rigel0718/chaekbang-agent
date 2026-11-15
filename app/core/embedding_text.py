"""임베딩 텍스트의 조립 규칙. 문자열만 다루고 어느 층의 모델도 모른다.

공식 서지 벡터(`app/central/embedding_text.py`)와 기관 도서 벡터
(`app/library/recommendation/embedding_text.py`)가 같은 규칙을 쓴다. 값이 같으면 층과 상관없이
같은 텍스트가 나온다. 규칙을 바꾸면 `TEXT_VERSION`을 올린다. 버전이 다른 벡터는 따로 저장된다.

버전 2: 서명(: 부제), 분류, 소개. 저자는 넣지 않는다. 저자는 고유명사라 기여자·저자 키와
서명·저자 찾기가 맡는다. 버전 1(`add-book-embeddings`)은 서명 다음 줄에 저자 원문을 넣었다.
"""

import hashlib
from collections.abc import Sequence
from enum import StrEnum

TEXT_VERSION = 2


class TextKind(StrEnum):
    """벡터가 어떤 텍스트로 만들어졌는지.

    DB에는 값 목록 제약이 없어 종류를 더해도 마이그레이션이 없다.
    """

    FULL = "full"  # 책 한 권을 벡터 하나로: 서명, 분류, 소개


def _clean(value: str | None) -> str:
    return " ".join(value.split()) if value else ""


def compose(
    kind: TextKind,
    *,
    title: str | None,
    subtitle: str | None,
    categories: Sequence[str | None],
    description: str | None,
) -> str:
    """서명(: 부제), 분류, 소개를 줄바꿈으로 잇는다. 빈 값은 건너뛴다.

    소개를 마지막에 둔다. 입력 길이 한도에서 잘릴 때 서명·분류가 남게 하기 위해서다.
    """
    if TextKind(kind) is not TextKind.FULL:
        raise ValueError(f"지원하지 않는 텍스트 종류: {kind}")
    head, sub = _clean(title), _clean(subtitle)
    lines = [
        f"{head}: {sub}" if head and sub else head or sub,
        " ".join(c for c in (_clean(c) for c in categories) if c),
        _clean(description),
    ]
    return "\n".join(line for line in lines if line)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
