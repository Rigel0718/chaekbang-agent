"""담은 책 응답. 책 값에 담은 시각만 더한다. 회원 값은 어디에도 없다."""

from datetime import datetime

from pydantic import BaseModel

from app.library.schemas.catalog import BookSummary


class BasketBook(BookSummary):
    added_at: datetime


class BasketRead(BaseModel):
    books: list[BasketBook]
