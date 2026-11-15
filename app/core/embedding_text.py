"""임베딩 텍스트의 조립 규칙. 문자열만 다루고 어느 층의 모델도 모른다.

공식 서지 벡터(`app/central/embedding_text.py`)와 기관 도서 벡터
(`app/library/recommendation/embedding_text.py`)가 같은 규칙을 쓴다. 값이 같으면 층과 상관없이
같은 텍스트가 나온다. 규칙을 바꾸면 `TEXT_VERSION`을 올린다. 버전이 다른 벡터는 따로 저장된다.

버전 2: 서명(: 부제), 분류, 소개. 저자는 넣지 않는다. 저자는 고유명사라 기여자·저자 키와
서명·저자 찾기가 맡는다. 버전 1(`add-book-embeddings`)은 서명 다음 줄에 저자 원문을 넣었다.

종류(`TextKind`)는 같은 규칙 안에서 어떤 필드를 넣는지다. 기본은 `full`이고 나머지는 추천 실험의
비교용이다(`add-recommendation-experiments`). 종류를 더해도 버전은 그대로다.
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
    WITH_AUTHOR = "with_author"  # 서명, 저자 원문, 분류, 소개 (버전 1과 같은 필드)
    DESCRIPTION = "description"  # 소개만
    TITLE = "title"  # 서명(: 부제)만. 필드별 벡터
    CATEGORY = "category"  # 분류만. 필드별 벡터


# 종류마다 넣는 줄. 순서는 늘 서명, 저자, 분류, 소개다.
_LINES: dict[TextKind, tuple[str, ...]] = {
    TextKind.FULL: ("title", "categories", "description"),
    TextKind.WITH_AUTHOR: ("title", "author", "categories", "description"),
    TextKind.DESCRIPTION: ("description",),
    TextKind.TITLE: ("title",),
    TextKind.CATEGORY: ("categories",),
}


def _clean(value: str | None) -> str:
    return " ".join(value.split()) if value else ""


def compose(
    kind: TextKind,
    *,
    title: str | None,
    subtitle: str | None,
    categories: Sequence[str | None],
    description: str | None,
    author: str | None = None,
) -> str:
    """종류가 정한 줄(서명(: 부제), 저자, 분류, 소개)을 줄바꿈으로 잇는다. 빈 값은 건너뛴다.

    소개를 마지막에 둔다. 입력 길이 한도에서 잘릴 때 서명·분류가 남게 하기 위해서다.
    그 종류의 값이 모두 비면 빈 문자열이다(적재가 벡터를 만들지 않는다).
    """
    head, sub = _clean(title), _clean(subtitle)
    lines = {
        "title": f"{head}: {sub}" if head and sub else head or sub,
        "author": _clean(author),
        "categories": " ".join(c for c in (_clean(c) for c in categories) if c),
        "description": _clean(description),
    }
    return "\n".join(lines[name] for name in _LINES[TextKind(kind)] if lines[name])


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
