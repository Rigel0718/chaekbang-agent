"""공식 서지와 그 기여자, 공식 서지 벡터. 운영자 층이 소유하고 기관 API로는 쓸 수 없다."""

from datetime import date
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    CHAR,
    CheckConstraint,
    Computed,
    Date,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.contributors import ContributorRole
from app.core.model_base import ISBN_PATTERN, Base, TimestampMixin, str_enum
from app.core.text import JAMO_STARTS_FUNCTION

# 벡터 열의 차원. 차원이 다른 모델을 넣으려면 마이그레이션이 필요하다. 두 층의 벡터가 같이 쓴다.
EMBEDDING_DIM = 1024


ADDITION_SYMBOL_PATTERN = "^[0-9]{5}$"  # ISBN 부가기호: 독자대상 1, 발행형태 1, 내용분류 3


class ExternalSource(StrEnum):
    """공식 서지의 출처. 채움은 셋을 함께 부르고 필드별 기준 출처로 합친다(`sources.py`)."""

    YES24 = "yes24"
    DATA4LIBRARY = "data4library"
    KAKAO = "kakao"


class Book(TimestampMixin, Base):
    """공식 서지. ISBN이 있는 책만 두고, 기관 API로는 쓸 수 없다."""

    __tablename__ = "books"
    __table_args__ = (
        CheckConstraint(f"isbn ~ '{ISBN_PATTERN}'", name="isbn_format"),
        CheckConstraint("list_price >= 0", name="list_price_nonnegative"),
        CheckConstraint(
            f"addition_symbol ~ '{ADDITION_SYMBOL_PATTERN}'", name="addition_symbol_format"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    isbn: Mapped[str] = mapped_column(CHAR(13), unique=True)
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str] = mapped_column(String(300))
    # 서명·저자 찾기 키(`app/core/text.py`의 `jamo_starts`). DB가 계산하고 코드는 쓰지 않는다
    title_jamo_starts: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text), Computed(f"{JAMO_STARTS_FUNCTION}(title)", persisted=True)
    )
    author_jamo_starts: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text), Computed(f"{JAMO_STARTS_FUNCTION}(author)", persisted=True)
    )
    publisher: Mapped[str | None] = mapped_column(String(200))
    published_date: Mapped[date | None] = mapped_column(Date)
    list_price: Mapped[int | None] = mapped_column(Integer)
    kdc: Mapped[str | None] = mapped_column(String(20))
    kdc_name: Mapped[str | None] = mapped_column(String(200))  # KDC 분류명 원문(정보나루)
    cover_url: Mapped[str | None] = mapped_column(String(1000))
    description: Mapped[str | None] = mapped_column(Text)
    subtitle: Mapped[str | None] = mapped_column(String(500))
    table_of_contents: Mapped[str | None] = mapped_column(Text)
    series_name: Mapped[str | None] = mapped_column(String(500))  # 표시용, 응답의 시리즈를 이은 것
    # 시리즈마다 `match_key`. 응답의 목록에서 계산한다(`create_official`).
    # 이은 문자열에서는 만들 수 없다(시리즈명에 쉼표가 들 수 있다)
    series_keys: Mapped[list[str]] = mapped_column(
        ARRAY(Text), server_default=text("'{}'"), default=list
    )
    # ISBN 부가기호 5자리. 첫 자리(독자대상)가 어린이 구분의 외부 근거다
    addition_symbol: Mapped[str | None] = mapped_column(CHAR(5))
    volume: Mapped[str | None] = mapped_column(String(50))  # 권 표기 원문
    # 서명·저자의 출처. 나머지 필드의 출처는 `field_sources`에 있다
    external_source: Mapped[ExternalSource | None] = mapped_column(
        str_enum(ExternalSource, "external_source")
    )
    # 값이 있는 필드마다 출처 이름(`{"list_price": "kakao"}`). YES24 하나로 만든 옛 행은 비어 있다
    field_sources: Mapped[dict[str, str]] = mapped_column(
        JSONB, server_default=text("'{}'"), default=dict
    )
    external_url: Mapped[str | None] = mapped_column(String(1000))
    external_category: Mapped[str | None] = mapped_column(String(100))  # 외부 분류 원문

    @property
    def cover_source(self) -> ExternalSource | None:
        """표지 URL의 출처. 필드별 출처가 없는 옛 행(YES24 하나)은 공식 서지의 출처다."""
        if not self.field_sources:
            return self.external_source
        source = self.field_sources.get("cover_url")
        return ExternalSource(source) if source else None


class BookContributor(TimestampMixin, Base):
    """공식 서지의 기여자 한 사람·한 역할. 저자 원문(`Book.author`)에서 다시 만들 수 있는 값이다.

    기관에 속하지 않는다(기관 공통 테이블). 공식 서지를 만드는 경로가 모두 `sync_contributors`로
    채운다.
    """

    __tablename__ = "book_contributors"
    __table_args__ = (
        UniqueConstraint("book_id", "position", name="uq_book_contributors_book_id_position"),
        CheckConstraint("name <> ''", name="name_not_empty"),
        CheckConstraint("name_key <> ''", name="name_key_not_empty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)  # 원문 순서, 0부터
    name: Mapped[str] = mapped_column(String(200))  # 저장용(`clean_spaces`)
    name_key: Mapped[str] = mapped_column(String(200), index=True)  # `match_key(name)`
    role: Mapped[ContributorRole] = mapped_column(str_enum(ContributorRole, "contributor_role"))
    role_text: Mapped[str | None] = mapped_column(String(50))  # 역할 원문(`글`, `기획`)


class OfficialBookEmbedding(TimestampMixin, Base):
    """공식 서지 벡터. 공식 서지, 모델, 텍스트 버전, 종류마다 하나. 공식 값만으로 만든다.

    기관에 속하지 않는다(기관 공통 테이블). 운영자 실행(`run_official_embedding`)만 쓰고, 공식
    서지에서 다시 만들 수 있는 값이다. 텍스트 원문은 두지 않고 해시만 둔다.
    """

    __tablename__ = "official_book_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "book_id",
            "model_name",
            "text_version",
            "kind",
            name="uq_official_book_embeddings_book_model_version_kind",
        ),
        CheckConstraint("kind <> ''", name="kind_not_empty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id", ondelete="CASCADE"))
    model_name: Mapped[str] = mapped_column(String(200))
    text_version: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(32))  # `app/core/embedding_text.py`의 `TextKind`
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    content_hash: Mapped[str] = mapped_column(CHAR(64))  # 임베딩 텍스트의 SHA-256
