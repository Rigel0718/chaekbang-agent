"""공식 서지와 그 기여자. 운영자 층이 소유하고 기관 API로는 쓸 수 없다."""

from datetime import date
from enum import StrEnum

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
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.core.contributors import ContributorRole
from app.core.model_base import ISBN_PATTERN, Base, TimestampMixin, str_enum
from app.core.text import JAMO_STARTS_FUNCTION


class ExternalSource(StrEnum):
    YES24 = "yes24"


class Book(TimestampMixin, Base):
    """공식 서지. ISBN이 있는 책만 두고, 기관 API로는 쓸 수 없다."""

    __tablename__ = "books"
    __table_args__ = (
        CheckConstraint(f"isbn ~ '{ISBN_PATTERN}'", name="isbn_format"),
        CheckConstraint("list_price >= 0", name="list_price_nonnegative"),
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
    cover_url: Mapped[str | None] = mapped_column(String(1000))
    description: Mapped[str | None] = mapped_column(Text)
    subtitle: Mapped[str | None] = mapped_column(String(500))
    table_of_contents: Mapped[str | None] = mapped_column(Text)
    series_name: Mapped[str | None] = mapped_column(String(500))
    external_source: Mapped[ExternalSource | None] = mapped_column(
        str_enum(ExternalSource, "external_source")
    )
    external_url: Mapped[str | None] = mapped_column(String(1000))
    external_category: Mapped[str | None] = mapped_column(String(100))  # 외부 분류 원문


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
