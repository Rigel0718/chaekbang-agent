"""기관 도서 벡터. 공식 서지에 연결되지 않은 책만 둔다. 텍스트 원문은 두지 않고 해시만 둔다.

연결된 책은 공식 서지 벡터(`app/central/models.py`의 `OfficialBookEmbedding`)를 쓴다.
"""

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CHAR,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.central.models import EMBEDDING_DIM
from app.core.model_base import Base, TimestampMixin


class BookEmbedding(TimestampMixin, Base):
    """기관 도서, 모델, 텍스트 버전, 종류마다 벡터 하나. 기관 도서에서 다시 만들 수 있는 값이다."""

    __tablename__ = "book_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "library_id",
            "library_book_id",
            "model_name",
            "text_version",
            "kind",
            name="uq_book_embeddings_library_book_model_version_kind",
        ),
        CheckConstraint("kind <> ''", name="kind_not_empty"),
        ForeignKeyConstraint(
            ["library_id", "library_book_id"],
            ["library_books.library_id", "library_books.id"],
            name="fk_book_embeddings_library_id_library_book_id_library_books",
            ondelete="CASCADE",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    library_id: Mapped[int] = mapped_column(ForeignKey("libraries.id", ondelete="RESTRICT"))
    library_book_id: Mapped[int] = mapped_column(Integer)
    model_name: Mapped[str] = mapped_column(String(200))
    text_version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))  # `app/core/embedding_text.py`의 `TextKind`
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    content_hash: Mapped[str] = mapped_column(CHAR(64))  # 임베딩 텍스트의 SHA-256
