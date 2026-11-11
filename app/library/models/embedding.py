"""기관 도서의 임베딩 벡터. 텍스트 원문은 두지 않고 해시만 둔다."""

from pgvector.sqlalchemy import Vector
from sqlalchemy import CHAR, ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.model_base import Base, TimestampMixin

# 벡터 열의 차원. 차원이 다른 모델을 넣으려면 마이그레이션이 필요하다.
EMBEDDING_DIM = 1024


class BookEmbedding(TimestampMixin, Base):
    """기관 도서, 모델, 텍스트 버전마다 벡터 하나. 기관 도서에서 다시 만들 수 있는 값이다."""

    __tablename__ = "book_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "library_id",
            "library_book_id",
            "model_name",
            "text_version",
            name="uq_book_embeddings_library_book_model_version",
        ),
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
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    content_hash: Mapped[str] = mapped_column(CHAR(64))  # 임베딩 텍스트의 SHA-256
