from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.schemas.common import Isbn, PatchModel, ReadModel, Won

NonEmpty = Annotated[str, Field(min_length=1)]


class BookBase(BaseModel):
    title: NonEmpty
    author: NonEmpty
    publisher: str | None = None
    published_date: date | None = None
    list_price: Won
    cover_url: str | None = None
    description: str | None = None


class BookCreate(BookBase):
    isbn: Isbn


class BookUpdate(PatchModel):
    """요청에 포함된 필드만 바꾼다. ISBN은 바꿀 수 없다."""

    NOT_NULL_FIELDS = ("title", "author", "list_price")

    title: NonEmpty | None = None
    author: NonEmpty | None = None
    publisher: str | None = None
    published_date: date | None = None
    list_price: Won | None = None
    cover_url: str | None = None
    description: str | None = None


class BookRead(ReadModel):
    isbn: str
    title: str
    author: str
    publisher: str | None
    published_date: date | None
    list_price: int
    cover_url: str | None
    description: str | None
    created_at: datetime
    updated_at: datetime


class InventoryCreate(BaseModel):
    isbn: Isbn
    quantity: Annotated[int, Field(ge=0, strict=True)]
    shelf_location: str | None = None


class InventoryUpdate(PatchModel):
    NOT_NULL_FIELDS = ("quantity",)

    quantity: Annotated[int, Field(ge=0, strict=True)] | None = None
    shelf_location: str | None = None


class InventoryRead(ReadModel):
    isbn: str
    quantity: int
    shelf_location: str | None
    title: str
    author: str
    updated_at: datetime
