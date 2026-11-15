"""공식 서지 벡터의 텍스트. 공식 서지의 값만 쓴다. 기관 값으로 빈칸을 채우지 않는다.

`Book`만 받으므로 기관 도서의 값이 들어갈 길이 없다(운영자 층은 기관 모델을 import하지 않는다).
"""

from app.central.models import Book
from app.core.embedding_text import TextKind, compose
from app.core.kdc import kdc_class_name


def official_embedding_text(book: Book, kind: TextKind = TextKind.FULL) -> str:
    return compose(
        kind,
        title=book.title,
        subtitle=book.subtitle,
        categories=[book.external_category, kdc_class_name(book.kdc)],
        description=book.description,
    )
