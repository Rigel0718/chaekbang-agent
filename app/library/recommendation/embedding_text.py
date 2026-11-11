"""기관 도서의 임베딩 텍스트. 구성이 자주 바뀔 곳이라 DB, 인코더, 설정을 모른다.

구성을 바꾸면 `TEXT_VERSION`을 올린다. 버전이 다른 벡터는 따로 저장돼 비교할 수 있다.
"""

import hashlib

from app.library.models.catalog import LibraryBook
from app.library.recommendation.kdc import kdc_class_name

TEXT_VERSION = 1


def _clean(value: str | None) -> str:
    return " ".join(value.split()) if value else ""


def build_embedding_text(book: LibraryBook) -> str:
    """표시 값(공식 값 먼저)의 서명, 저자, 분류, 소개를 줄바꿈으로 잇는다. 빈 값은 건너뛴다.

    소개를 마지막에 둔다. 입력 길이 한도에서 잘릴 때 서명·저자·분류가 남게 하기 위해서다.
    """
    official = book.book  # 부제와 외부 분류 원문은 공식 서지에만 있다
    title = _clean(book.shown("title"))
    subtitle = _clean(official.subtitle) if official is not None else ""
    categories = [
        _clean(official.external_category) if official is not None else "",
        kdc_class_name(book.shown("kdc")) or "",
    ]
    lines = [
        f"{title}: {subtitle}" if title and subtitle else title or subtitle,
        _clean(book.shown("author")),
        " ".join(c for c in categories if c),
        _clean(book.shown("description")),
    ]
    return "\n".join(line for line in lines if line)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
