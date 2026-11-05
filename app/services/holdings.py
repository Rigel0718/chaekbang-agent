"""소장 사본 service. 모든 함수는 로그인한 기관(library_id) 범위 안에서만 동작한다."""

from sqlalchemy import exists, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import AcquisitionType, Book, Holding, HoldingSource, HoldingStatus
from app.models.circulation import Loan
from app.schemas.catalog import HoldingCreate, HoldingUpdate, check_acquisition
from app.services.books import get_book
from app.services.errors import ConflictError, InvalidRequestError
from app.services.tenancy import get_owned

LABEL = "사본"


def _duplicate(accession_number: str) -> ConflictError:
    return ConflictError(f"이미 쓰는 등록번호입니다: {accession_number}")


def _require_isbn_for_purchase(book: Book, acquisition_type: AcquisitionType) -> None:
    if acquisition_type == AcquisitionType.PURCHASED and book.isbn is None:
        raise InvalidRequestError(
            "매입·납품 사본은 ISBN이 있는 도서로만 등록할 수 있습니다. 도서의 ISBN을 먼저 채우세요"
        )


async def _ensure_accession_free(
    session: AsyncSession, library_id: int, accession_number: str, *, except_id: int | None = None
) -> None:
    query = select(Holding.id).where(
        Holding.library_id == library_id, Holding.accession_number == accession_number
    )
    if except_id is not None:
        query = query.where(Holding.id != except_id)
    if await session.scalar(query) is not None:
        raise _duplicate(accession_number)


async def _commit(session: AsyncSession, accession_number: str) -> None:
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _duplicate(accession_number) from exc


async def create_holding(session: AsyncSession, library_id: int, data: HoldingCreate) -> Holding:
    if data.status == HoldingStatus.ON_LOAN:
        raise ConflictError("대출 중 상태는 대출로만 바뀝니다")
    book = await get_book(session, data.book_id)
    _require_isbn_for_purchase(book, data.acquisition_type)
    await _ensure_accession_free(session, library_id, data.accession_number)
    holding = Holding(library_id=library_id, source=HoldingSource.MANUAL, **data.model_dump())
    session.add(holding)
    await _commit(session, data.accession_number)
    return await get_holding(session, library_id, holding.id)


async def get_holding(session: AsyncSession, library_id: int, holding_id: int) -> Holding:
    holding = await get_owned(session, Holding, library_id, holding_id, label=LABEL)
    await session.refresh(holding)
    return holding


async def list_holdings(
    session: AsyncSession,
    library_id: int,
    *,
    limit: int,
    offset: int,
    book_id: int | None = None,
    status: HoldingStatus | None = None,
) -> tuple[list[Holding], int]:
    where = [Holding.library_id == library_id]
    if book_id is not None:
        where.append(Holding.book_id == book_id)
    if status is not None:
        where.append(Holding.status == status)
    total = await session.scalar(select(func.count()).select_from(Holding).where(*where))
    rows = await session.scalars(
        select(Holding)
        .where(*where)
        .order_by(Holding.accession_number, Holding.id)
        .limit(limit)
        .offset(offset)
    )
    return list(rows), total or 0


async def update_holding(
    session: AsyncSession, library_id: int, holding_id: int, data: HoldingUpdate
) -> Holding:
    holding = await get_owned(session, Holding, library_id, holding_id, label=LABEL)
    changes = data.changes()

    new_status = changes.get("status")
    if new_status is not None and new_status != holding.status:
        if new_status == HoldingStatus.ON_LOAN:
            raise ConflictError("대출 중 상태는 대출로만 바뀝니다")
        if holding.status == HoldingStatus.ON_LOAN:
            raise ConflictError("대출 중인 사본입니다. 반납을 먼저 처리하세요")

    acquisition_keys = {"acquisition_type", "purchase_price", "donor"}
    if acquisition_keys & changes.keys():
        merged = {k: changes.get(k, getattr(holding, k)) for k in acquisition_keys}
        try:
            check_acquisition(merged["acquisition_type"], merged["purchase_price"], merged["donor"])
        except ValueError as exc:
            raise InvalidRequestError(str(exc)) from exc
        _require_isbn_for_purchase(holding.book, merged["acquisition_type"])

    if "accession_number" in changes:
        await _ensure_accession_free(
            session, library_id, changes["accession_number"], except_id=holding_id
        )
    for field, value in changes.items():
        setattr(holding, field, value)
    await _commit(session, holding.accession_number)
    return await get_holding(session, library_id, holding_id)


async def delete_holding(session: AsyncSession, library_id: int, holding_id: int) -> None:
    """대출 기록이 있는 사본은 지울 수 없다. 대신 상태를 lost나 damaged로 바꾼다."""
    holding = await get_owned(session, Holding, library_id, holding_id, label=LABEL)
    if await session.scalar(select(exists().where(Loan.holding_id == holding_id))):
        raise ConflictError(
            "대출 기록이 있는 사본은 삭제할 수 없습니다. 상태를 분실·훼손으로 바꾸세요"
        )
    await session.delete(holding)
    await session.commit()
