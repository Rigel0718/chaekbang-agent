"""catalog 컨텍스트 (공유 커널): 도서와 매장 재고. 다른 컨텍스트를 참조하지 않는다."""

from datetime import date

from sqlalchemy import CHAR, CheckConstraint, Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import ISBN_PATTERN, Base, TimestampMixin


class Book(TimestampMixin, Base):
    __tablename__ = "books"
    __table_args__ = (
        CheckConstraint(f"isbn ~ '{ISBN_PATTERN}'", name="isbn_format"),
        CheckConstraint("list_price >= 0", name="list_price_nonnegative"),
    )

    isbn: Mapped[str] = mapped_column(CHAR(13), primary_key=True)
    title: Mapped[str] = mapped_column(String(500))
    author: Mapped[str] = mapped_column(String(300))
    publisher: Mapped[str | None] = mapped_column(String(200))
    published_date: Mapped[date | None] = mapped_column(Date)
    list_price: Mapped[int] = mapped_column(Integer)
    cover_url: Mapped[str | None] = mapped_column(String(1000))
    description: Mapped[str | None] = mapped_column(Text)


class StoreInventory(TimestampMixin, Base):
    __tablename__ = "store_inventory"
    __table_args__ = (CheckConstraint("quantity >= 0", name="quantity_nonnegative"),)

    isbn: Mapped[str] = mapped_column(
        CHAR(13), ForeignKey("books.isbn", ondelete="RESTRICT"), primary_key=True
    )
    quantity: Mapped[int] = mapped_column(Integer)
    shelf_location: Mapped[str | None] = mapped_column(String(100))

    book: Mapped[Book] = relationship(lazy="joined")

    @property
    def title(self) -> str:
        return self.book.title

    @property
    def author(self) -> str:
        return self.book.author
