from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import AdminStaff, CurrentStaff, Session
from app.core.isbn import InvalidIsbnError, normalize_isbn
from app.models.catalog import Audience
from app.schemas.catalog import BookCreate, BookRead, BookUpdate, BookWithHoldings
from app.schemas.common import Page, Pagination
from app.services import books
from app.services.books import BookCounts

router = APIRouter(prefix="/books", tags=["books"])


def _view(row: BookCounts) -> BookWithHoldings:
    return BookWithHoldings(
        **BookRead.model_validate(row.book).model_dump(),
        holding_count=row.holding_count,
        available_count=row.available_count,
    )


def _query_isbn(isbn: str | None) -> str | None:
    """쿼리의 ISBN도 본문과 같은 규칙으로 정규화한다."""
    if isbn is None:
        return None
    try:
        return normalize_isbn(isbn)
    except InvalidIsbnError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc


@router.post("", status_code=status.HTTP_201_CREATED, response_model=BookRead)
async def create_book(data: BookCreate, staff: AdminStaff, session: Session):
    return await books.create_book(session, data)


@router.get("", response_model=Page[BookWithHoldings])
async def list_books(
    staff: CurrentStaff,
    session: Session,
    page: Annotated[Pagination, Query()],
    isbn: Annotated[str | None, Query(description="하이픈이 있어도 된다")] = None,
    held: Annotated[bool, Query(description="true면 우리 기관에 사본이 있는 도서만")] = False,
    audience: Audience | None = None,
):
    rows, total = await books.list_books(
        session,
        staff.library_id,
        limit=page.limit,
        offset=page.offset,
        isbn=_query_isbn(isbn),
        held=held,
        audience=audience,
    )
    return Page[BookWithHoldings](
        items=[_view(r) for r in rows], total=total, limit=page.limit, offset=page.offset
    )


@router.get("/{book_id}", response_model=BookWithHoldings)
async def get_book(book_id: int, staff: CurrentStaff, session: Session):
    return _view(await books.get_book_with_counts(session, staff.library_id, book_id))


@router.patch("/{book_id}", response_model=BookRead)
async def update_book(book_id: int, data: BookUpdate, staff: AdminStaff, session: Session):
    return await books.update_book(session, book_id, data)


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_book(book_id: int, staff: AdminStaff, session: Session) -> None:
    await books.delete_book(session, book_id)
