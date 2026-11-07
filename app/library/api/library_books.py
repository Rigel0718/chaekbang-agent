from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status

from app.core.deps import AdminStaff, CurrentStaff, Session
from app.core.isbn import InvalidIsbnError, normalize_isbn
from app.models.catalog import Audience, LibraryBook
from app.schemas.catalog import (
    AudienceRefreshResult,
    LibraryBookCreate,
    LibraryBookRead,
    LibraryBookUpdate,
    LibraryBookWithHoldings,
)
from app.schemas.common import Page, Pagination
from app.services import library_books
from app.services.library_books import LibraryBookCounts

router = APIRouter(prefix="/library-books", tags=["library-books"])


def _read(library_book: LibraryBook) -> LibraryBookRead:
    return LibraryBookRead(**LibraryBookRead.of(library_book))


def _view(row: LibraryBookCounts) -> LibraryBookWithHoldings:
    return LibraryBookWithHoldings(
        **LibraryBookRead.of(row.library_book),
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


@router.post("", status_code=status.HTTP_201_CREATED, response_model=LibraryBookRead)
async def create_library_book(data: LibraryBookCreate, staff: AdminStaff, session: Session):
    return _read(await library_books.create_library_book(session, staff.library_id, data))


@router.get("", response_model=Page[LibraryBookWithHoldings])
async def list_library_books(
    staff: CurrentStaff,
    session: Session,
    page: Annotated[Pagination, Query()],
    isbn: Annotated[str | None, Query(description="하이픈이 있어도 된다")] = None,
    held: Annotated[bool, Query(description="true면 제적이 아닌 사본이 있는 도서만")] = False,
    audience: Audience | None = None,
):
    rows, total = await library_books.list_library_books(
        session,
        staff.library_id,
        limit=page.limit,
        offset=page.offset,
        isbn=_query_isbn(isbn),
        held=held,
        audience=audience,
    )
    return Page[LibraryBookWithHoldings](
        items=[_view(r) for r in rows], total=total, limit=page.limit, offset=page.offset
    )


@router.post("/audience/refresh", response_model=AudienceRefreshResult)
async def refresh_audience(staff: AdminStaff, session: Session):
    """공식 서지가 채워진 뒤 자기 기관의 어린이 구분을 갱신한다."""
    updated = await library_books.refresh_audience(session, staff.library_id)
    return AudienceRefreshResult(updated=updated)


@router.get("/{library_book_id}", response_model=LibraryBookWithHoldings)
async def get_library_book(library_book_id: int, staff: CurrentStaff, session: Session):
    return _view(
        await library_books.get_library_book_with_counts(session, staff.library_id, library_book_id)
    )


@router.patch("/{library_book_id}", response_model=LibraryBookRead)
async def update_library_book(
    library_book_id: int, data: LibraryBookUpdate, staff: AdminStaff, session: Session
):
    return _read(
        await library_books.update_library_book(session, staff.library_id, library_book_id, data)
    )


@router.delete("/{library_book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_library_book(library_book_id: int, staff: AdminStaff, session: Session) -> None:
    await library_books.delete_library_book(session, staff.library_id, library_book_id)
