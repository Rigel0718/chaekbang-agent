"""소장 사본 service. 모든 함수는 로그인한 기관(library_id) 범위 안에서만 동작한다."""

from sqlalchemy import case, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.models import Book
from app.core.errors import ConflictError, InvalidRequestError
from app.core.tenancy import get_owned
from app.core.text import korean_order
from app.library.models.catalog import (
    AcquisitionType,
    Holding,
    HoldingSource,
    HoldingStatus,
    LibraryBook,
)
from app.library.models.circulation import Loan
from app.library.schemas.catalog import HoldingCreate, HoldingUpdate, check_acquisition
from app.library.services.library_books import get_library_book

LABEL = "책"


def _duplicate(accession_number: str) -> ConflictError:
    return ConflictError(f"이미 쓰는 등록번호예요: {accession_number}")


def _require_isbn_for_purchase(
    library_book: LibraryBook, acquisition_type: AcquisitionType
) -> None:
    if acquisition_type == AcquisitionType.PURCHASED and library_book.isbn is None:
        raise InvalidRequestError(
            "매입·납품한 책은 ISBN이 있어야 등록할 수 있어요. ISBN을 먼저 넣어 주세요."
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
        raise ConflictError("대출 중 상태는 빌리기·반납으로만 바뀌어요.")
    library_book = await get_library_book(session, library_id, data.library_book_id)
    _require_isbn_for_purchase(library_book, data.acquisition_type)
    await _ensure_accession_free(session, library_id, data.accession_number)
    holding = Holding(library_id=library_id, source=HoldingSource.MANUAL, **data.model_dump())
    session.add(holding)
    await _commit(session, data.accession_number)
    return await get_holding(session, library_id, holding.id)


def missing_fields(holding: Holding) -> list[str]:
    """매입 사본에 빠진 정보. 정보를 채우면 바로 사라지도록 저장하지 않고 계산한다."""
    if holding.acquisition_type != AcquisitionType.PURCHASED:
        return []
    missing = []
    if holding.library_book.isbn is None:
        missing.append("isbn")
    if holding.purchase_price is None:
        missing.append("purchase_price")
    return missing


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
    library_book_id: int | None = None,
    status: HoldingStatus | None = None,
    incomplete: bool = False,
    q: str | None = None,
) -> tuple[list[Holding], int]:
    """status를 주지 않으면 제적 사본을 뺀다. incomplete=True면 빠진 정보가 있는 사본만.

    q가 있으면 등록번호가 q와 같거나, 기관 값·공식 서지 서명·저자에 q가 든 사본만이다
    (대소문자 무시, `%`·`_`는 글자 그대로). 분실·제적 사본을 되돌리려고 찾는 것이라 q만 있으면
    제적도 넣는다. 등록번호가 같은 사본 → 표시 서명 가나다순 → 등록번호 순이다.
    """
    where = [Holding.library_id == library_id]
    if library_book_id is not None:
        where.append(Holding.library_book_id == library_book_id)
    if status is not None:
        where.append(Holding.status == status)
    elif q is None:
        where.append(Holding.status != HoldingStatus.WITHDRAWN)
    if q is not None:
        where.append(
            or_(
                Holding.accession_number == q,
                LibraryBook.title.icontains(q, autoescape=True),
                LibraryBook.author.icontains(q, autoescape=True),
                Book.title.icontains(q, autoescape=True),
                Book.author.icontains(q, autoescape=True),
            )
        )
    if incomplete:
        where.append(Holding.acquisition_type == AcquisitionType.PURCHASED)
        where.append(
            or_(
                Holding.purchase_price.is_(None),
                Holding.library_book.has(LibraryBook.isbn.is_(None)),
            )
        )
    # q가 없으면 최근에 등록한 사본부터(관리자 화면 [장서]의 처음 목록)
    order = [Holding.created_at.desc(), Holding.id.desc()]
    if q is not None:
        shown_title = func.coalesce(Book.title, LibraryBook.title)
        exact_first = case((Holding.accession_number == q, 0), else_=1)
        order = [exact_first, korean_order(shown_title), Holding.accession_number, Holding.id]

    def scoped(query):
        # q는 도서 값을 읽으므로 기관 도서와 공식 서지를 붙인다. 기관 도서는 같은 기관 것만 있다.
        if q is None:
            return query
        return query.join(LibraryBook, LibraryBook.id == Holding.library_book_id).outerjoin(
            Book, Book.id == LibraryBook.book_id
        )

    total = await session.scalar(scoped(select(func.count()).select_from(Holding)).where(*where))
    rows = await session.scalars(
        scoped(select(Holding)).where(*where).order_by(*order).limit(limit).offset(offset)
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
            raise ConflictError("대출 중 상태는 빌리기·반납으로만 바뀌어요.")
        if holding.status == HoldingStatus.ON_LOAN:
            raise ConflictError("대출 중인 책이에요. 먼저 반납해 주세요.")

    acquisition_keys = {"acquisition_type", "purchase_price", "donor"}
    if acquisition_keys & changes.keys():
        merged = {k: changes.get(k, getattr(holding, k)) for k in acquisition_keys}
        # 이미 매입인 가져온 사본은 빠진 정보를 하나씩 채울 수 있어야 한다.
        imported_purchase = (
            holding.source == HoldingSource.IMPORTED
            and holding.acquisition_type == AcquisitionType.PURCHASED
            and merged["acquisition_type"] == AcquisitionType.PURCHASED
        )
        try:
            check_acquisition(
                merged["acquisition_type"],
                merged["purchase_price"],
                merged["donor"],
                imported_purchase=imported_purchase,
            )
        except ValueError as exc:
            raise InvalidRequestError(str(exc)) from exc
        if not imported_purchase:
            _require_isbn_for_purchase(holding.library_book, merged["acquisition_type"])

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
            "대출 기록이 있는 책은 삭제할 수 없어요. 상태를 분실이나 훼손으로 바꿔 주세요."
        )
    await session.delete(holding)
    await session.commit()
