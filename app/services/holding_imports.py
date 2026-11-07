"""장서 가져오기 service: 미리 보기, 적용, 기록 조회.

REST 라우터와 이후 운영 에이전트의 import_holdings tool이 함께 쓴다.
"""

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.importing.columns import find_header
from app.importing.errors import ImportFileError
from app.importing.normalize import clean_text
from app.importing.reader import read_table
from app.importing.rows import FLAG_NO_ISBN, FLAG_NO_PRICE, acquisition_flags, parse_rows
from app.models.catalog import (
    AcquisitionType,
    Audience,
    AudienceSource,
    Book,
    Holding,
    HoldingImport,
    HoldingSource,
    HoldingStatus,
    ImportStatus,
    LibraryBook,
)
from app.models.library import Library, LoanMode
from app.services.errors import ConflictError, InvalidRequestError
from app.services.library_books import apply_official
from app.services.tenancy import get_owned

LABEL = "가져오기 기록"
# 파일 근거가 덮어쓰는 근거. 저장 전 새 도서는 None이다.
FILE_LABEL_REPLACES = (None, AudienceSource.DEFAULT, AudienceSource.EXTERNAL_CATEGORY)
INTERNAL_LIBRARY = "장서 가져오기는 기존 대출 프로그램을 쓰는 기관만 할 수 있습니다"


class Outcome(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    UNCHANGED = "unchanged"
    SKIPPED = "skipped"


@dataclass
class Snapshot:
    """비교에 쓰는 현재 장서. 적용 중에 만든 도서도 여기에 더해 같은 파일의 뒤 행이 다시 쓴다."""

    holdings: dict[str, Holding]
    books_by_isbn: dict[str, LibraryBook]  # 기관 도서
    books_without_isbn: dict[tuple[str, str], LibraryBook]
    officials: dict[str, Book]  # 행의 ISBN에 맞는 공식 서지


@dataclass
class RowPlan:
    outcome: Outcome
    flags: list[str]
    values: dict[str, Any] = field(default_factory=dict)  # 사본에 넣을 값
    book: LibraryBook | None = None  # 찾은 기관 도서. None이면 새로 만든다


def _book_key(title: str | None, author: str | None) -> tuple[str, str]:
    return clean_text(title) or "", clean_text(author) or ""


async def _snapshot(session: AsyncSession, library_id: int, rows: list[dict[str, Any]]) -> Snapshot:
    holdings = await session.scalars(select(Holding).where(Holding.library_id == library_id))
    isbns = {row["isbn"] for row in rows if row["isbn"]}
    own = select(LibraryBook).where(LibraryBook.library_id == library_id)
    with_isbn = await session.scalars(own.where(LibraryBook.isbn.in_(isbns))) if isbns else []
    without_isbn = await session.scalars(own.where(LibraryBook.isbn.is_(None)))
    officials = await session.scalars(select(Book).where(Book.isbn.in_(isbns))) if isbns else []
    return Snapshot(
        holdings={h.accession_number: h for h in holdings},
        books_by_isbn={b.isbn: b for b in with_isbn},
        books_without_isbn={_book_key(b.title, b.author): b for b in without_isbn},
        officials={b.isbn: b for b in officials},
    )


def _find_book(row: dict[str, Any], holding: Holding | None, snap: Snapshot) -> LibraryBook | None:
    if row["isbn"]:
        return snap.books_by_isbn.get(row["isbn"])
    if holding is not None:
        return holding.library_book  # 파일에 ISBN이 없으면 지금 도서를 유지한다
    return snap.books_without_isbn.get(_book_key(row["title"], row["author"]))


def _holding_values(row: dict[str, Any], holding: Holding | None) -> dict[str, Any]:
    """파일 값을 사본 값으로 바꾼다. 파일에 없는 값은 기존 값을 유지한다."""
    was = holding
    acquisition = (
        AcquisitionType(row["acquisition"])
        if row["acquisition"]
        else (was.acquisition_type if was else AcquisitionType.UNKNOWN)
    )
    price = donor = None
    if acquisition == AcquisitionType.PURCHASED:
        kept = was.purchase_price if was and was.acquisition_type == acquisition else None
        price = row["price"] if row["price"] is not None else kept
    elif acquisition == AcquisitionType.DONATED:
        kept = was.donor if was and was.acquisition_type == acquisition else None
        donor = row["donor"] or kept

    if row["status"]:
        status = HoldingStatus(row["status"])
    elif was is None or was.status == HoldingStatus.WITHDRAWN:
        status = HoldingStatus.AVAILABLE  # 새 사본이거나 파일에 다시 나타난 제적 사본
    else:
        status = was.status

    return {
        "call_number": row["call_number"] or (was.call_number if was else None),
        "shelf_location": row["shelf_location"] or (was.shelf_location if was else None),
        "status": status,
        "acquisition_type": acquisition,
        "purchase_price": price,
        "donor": donor,
        "source": HoldingSource.IMPORTED,
    }


def _plan_row(row: dict[str, Any], snap: Snapshot) -> RowPlan:
    file_flags = [f for f in row["flags"] if f not in (FLAG_NO_ISBN, FLAG_NO_PRICE)]
    if row["skip_reason"]:
        return RowPlan(Outcome.SKIPPED, file_flags)

    holding = snap.holdings.get(row["accession_number"])
    book = _find_book(row, holding, snap)
    values = _holding_values(row, holding)
    has_isbn = bool(row["isbn"] or (book is not None and book.isbn))
    flags = file_flags + acquisition_flags(
        values["acquisition_type"], has_isbn, values["purchase_price"] is not None
    )
    if holding is None:
        return RowPlan(Outcome.CREATE, flags, values, book)
    changed = book is None or book.id != holding.library_book_id
    changed = changed or any(getattr(holding, k) != v for k, v in values.items())
    return RowPlan(Outcome.UPDATE if changed else Outcome.UNCHANGED, flags, values, book)


def _missing(rows: list[dict[str, Any]], snap: Snapshot) -> tuple[list[Holding], int]:
    """(파일에서 빠진 사본, 비교 대상 수). 대상은 가져온 사본 중 제적이 아닌 것이다.

    건너뛴 행의 등록번호도 파일에 있는 것으로 친다.
    """
    in_file = {row["accession_number"] for row in rows if row["accession_number"]}
    base = [
        h
        for h in snap.holdings.values()
        if h.source == HoldingSource.IMPORTED and h.status != HoldingStatus.WITHDRAWN
    ]
    return [h for h in base if h.accession_number not in in_file], len(base)


def _summarize(rows: list[dict[str, Any]], missing_count: int, base_count: int) -> dict[str, Any]:
    outcomes = {outcome.value: 0 for outcome in Outcome}
    flags: dict[str, int] = {}
    for row in rows:
        outcomes[row["outcome"]] += 1
        for flag in row["flags"]:
            flags[flag] = flags.get(flag, 0) + 1
    return {
        "total": len(rows),
        **outcomes,
        "flags": flags,
        "missing_count": missing_count,
        "compared_count": base_count,
    }


def _record_plans(rows: list[dict[str, Any]], plans: list[RowPlan]) -> list[dict[str, Any]]:
    return [
        {**row, "outcome": plan.outcome.value, "flags": plan.flags}
        for row, plan in zip(rows, plans, strict=True)
    ]


async def _require_imported_library(session: AsyncSession, library_id: int, *, lock: bool) -> None:
    query = select(Library).where(Library.id == library_id)
    library = await session.scalar(query.with_for_update() if lock else query)
    assert library is not None
    if library.loan_mode != LoanMode.IMPORTED:
        raise ConflictError(INTERNAL_LIBRARY)


async def create_preview(
    session: AsyncSession,
    library_id: int,
    staff_id: int,
    filename: str,
    content: bytes,
    column_overrides: dict[str, str] | None = None,
) -> HoldingImport:
    """파일을 해석해 미리 보기를 저장한다. 장서는 바꾸지 않는다."""
    await _require_imported_library(session, library_id, lock=False)
    try:
        table = read_table(filename, content)
        match = find_header(table, column_overrides)
    except ImportFileError as exc:
        raise InvalidRequestError(exc.message, **exc.extra) from exc

    rows = [row.to_dict() for row in parse_rows(table, match)]
    snap = await _snapshot(session, library_id, rows)
    plans = [_plan_row(row, snap) for row in rows]
    rows = _record_plans(rows, plans)
    missing, base = _missing(rows, snap)

    record = HoldingImport(
        library_id=library_id,
        staff_user_id=staff_id,
        filename=filename[:300],
        column_mapping=match.mapping,
        rows=rows,
        summary=_summarize(rows, len(missing), base),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


def _new_book(library_id: int, row: dict[str, Any], snap: Snapshot) -> LibraryBook:
    """기관 도서만 만든다. 파일 값은 공식 서지에 쓰지 않고, 같은 ISBN이 있으면 연결한다."""
    book = LibraryBook(
        library_id=library_id,
        isbn=row["isbn"],
        title=row["title"],
        author=row["author"],
    )
    apply_official(book, snap.officials.get(row["isbn"]))
    if row["isbn"]:
        snap.books_by_isbn[row["isbn"]] = book
    else:
        snap.books_without_isbn[_book_key(row["title"], row["author"])] = book
    return book


def _fill_book(book: LibraryBook, row: dict[str, Any]) -> None:
    """이미 있는 값은 파일 값으로 덮어쓰지 않고 빈 필드만 채운다."""
    if book.publisher is None:
        book.publisher = row["publisher"]
    if book.kdc is None:
        book.kdc = row["kdc"]
    if book.published_date is None and row["published_date"]:
        book.published_date = date.fromisoformat(row["published_date"])
    # 관리자 지정(manual)은 바꾸지 않는다. 근거가 없는 행은 값을 내리지 않는다.
    if row["children"] and book.audience_source in FILE_LABEL_REPLACES:
        book.audience = Audience.CHILDREN
        book.audience_source = AudienceSource.IMPORT_LABEL


def _apply_row(
    session: AsyncSession, library_id: int, row: dict[str, Any], plan: RowPlan, snap: Snapshot
) -> None:
    book = plan.book or _find_book(row, snap.holdings.get(row["accession_number"]), snap)
    if book is None:
        book = _new_book(library_id, row, snap)
    _fill_book(book, row)

    holding = snap.holdings.get(row["accession_number"])
    if holding is None:
        holding = Holding(library_id=library_id, accession_number=row["accession_number"])
        session.add(holding)
        snap.holdings[row["accession_number"]] = holding
    holding.library_book = book
    for name, value in plan.values.items():
        setattr(holding, name, value)
    holding.last_synced_at = clock.now()


async def apply_import(
    session: AsyncSession, library_id: int, import_id: int, *, confirm_withdraw: bool = False
) -> HoldingImport:
    """저장된 행을 현재 장서와 다시 비교해 한 트랜잭션으로 적용한다."""
    await _require_imported_library(session, library_id, lock=True)
    record = await get_owned(session, HoldingImport, library_id, import_id, label=LABEL)
    await session.refresh(record)  # 기관 행을 잠근 뒤의 상태로 판단한다
    if record.status == ImportStatus.APPLIED:
        raise ConflictError("이미 적용한 가져오기입니다")

    rows = record.rows
    snap = await _snapshot(session, library_id, rows)
    missing, base = _missing(rows, snap)
    if missing and len(missing) * 2 >= base and not confirm_withdraw:
        raise ConflictError(
            f"파일에서 빠진 사본이 {len(missing)}권으로 전체 {base}권의 절반 이상입니다. "
            "파일이 맞으면 confirm_withdraw=true로 다시 적용하세요"
        )

    plans = [_plan_row(row, snap) for row in rows]
    for row, plan in zip(rows, plans, strict=True):
        if plan.outcome != Outcome.SKIPPED:
            _apply_row(session, library_id, row, plan, snap)
    for holding in missing:
        holding.status = HoldingStatus.WITHDRAWN

    rows = _record_plans(rows, plans)
    record.rows = rows
    record.summary = _summarize(rows, len(missing), base)
    record.status = ImportStatus.APPLIED
    record.applied_at = clock.now()
    try:
        await session.commit()
    except IntegrityError as exc:
        # 같은 기관의 직접 등록이 같은 ISBN의 도서를 먼저 만든 경우다.
        await session.rollback()
        raise ConflictError("다른 작업과 겹쳤습니다. 다시 적용해 주세요") from exc
    await session.refresh(record)
    return record


async def get_import(session: AsyncSession, library_id: int, import_id: int) -> HoldingImport:
    return await get_owned(session, HoldingImport, library_id, import_id, label=LABEL)


async def list_imports(
    session: AsyncSession, library_id: int, *, limit: int, offset: int
) -> tuple[list[HoldingImport], int]:
    where = HoldingImport.library_id == library_id
    total = await session.scalar(select(func.count()).select_from(HoldingImport).where(where))
    rows = await session.scalars(
        select(HoldingImport)
        .where(where)
        .order_by(HoldingImport.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows), total or 0


async def list_rows(
    session: AsyncSession,
    library_id: int,
    import_id: int,
    *,
    limit: int,
    offset: int,
    outcome: Outcome | None = None,
    flag: str | None = None,
) -> tuple[list[dict[str, Any]], int]:
    record = await get_import(session, library_id, import_id)
    rows = [
        row
        for row in record.rows
        if (outcome is None or row["outcome"] == outcome) and (flag is None or flag in row["flags"])
    ]
    return rows[offset : offset + limit], len(rows)
