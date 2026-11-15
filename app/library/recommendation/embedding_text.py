"""기관 도서 벡터의 텍스트. 공식 서지에 연결되지 않은 책(ISBN 없음, 못 찾음)에 쓴다.

기관 값만 쓴다(`shown`을 쓰지 않는다). 연결된 책은 공식 서지 벡터를 쓴다
(`app/central/embedding_text.py`). 조립 규칙은 `app/core/embedding_text.py` 한 곳에 있다.
"""

from app.core.embedding_text import TextKind, compose
from app.core.kdc import kdc_class_name
from app.library.models.catalog import LibraryBook


def library_embedding_text(book: LibraryBook, kind: TextKind = TextKind.FULL) -> str:
    return compose(
        kind,
        title=book.title,
        subtitle=None,  # 기관 도서에는 부제 칸이 없다
        categories=[kdc_class_name(book.kdc)],
        description=book.description,
    )
