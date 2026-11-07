"""어린이 구분 저장소. 근거가 있는 기관 도서만 행이 있고, 없으면 general, default다."""

from enum import StrEnum

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.model_base import Base, TimestampMixin, str_enum


class Audience(StrEnum):
    CHILDREN = "children"
    GENERAL = "general"


class AudienceSource(StrEnum):
    DEFAULT = "default"  # 근거 없음. 저장하지 않는다
    MANUAL = "manual"  # 관리자 지정
    IMPORT_LABEL = "import_label"  # 가져온 파일의 별치기호·자료실·부가기호
    EXTERNAL_CATEGORY = "external_category"  # 연결된 공식 서지의 분류 원문


class LibraryBookAudience(TimestampMixin, Base):
    __tablename__ = "library_book_audiences"
    __table_args__ = (
        ForeignKeyConstraint(
            ["library_id", "library_book_id"],
            ["library_books.library_id", "library_books.id"],
            name="fk_library_book_audiences_library_id_library_book_id",
            ondelete="CASCADE",
        ),
        CheckConstraint("audience_source <> 'default'", name="source_not_default"),
    )

    library_id: Mapped[int] = mapped_column(
        ForeignKey("libraries.id", ondelete="RESTRICT"), primary_key=True
    )
    library_book_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    audience: Mapped[Audience] = mapped_column(str_enum(Audience, "audience"))
    audience_source: Mapped[AudienceSource] = mapped_column(
        str_enum(AudienceSource, "audience_source")
    )
