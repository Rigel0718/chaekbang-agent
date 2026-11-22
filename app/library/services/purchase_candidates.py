"""구매 후보 service: 희망도서(ISBN별), 인기, 분야 숫자.

코드가 "살 책"으로 내놓을 수 있는 것은 희망도서와 이미 가진 책의 복본뿐이다(소장하지 않은 책의 외부
후보는 없다). 부족 분야는 숫자만 내고 책은 관리자가 ISBN으로 넣는다. 가격과 회원 값은 이 service
어디에도 없다. REST와 운영 에이전트 tool(`purchase_tools.py`)이 같은 함수를 부른다.

- 희망도서: `requested`이고 ISBN이 있고 지금 그 기관이 소장하지 않은 신청을 ISBN별로 묶는다.
  ISBN 없는 처리 전 신청은 건수만 센다.
- 인기, 자체 대출: 기간(기본 최근 90일) 대출 수 순서의 책. 제적 아닌 사본이 있고 ISBN이 있어야 한다.
- 인기, 외부 대출: 대출 기록이 없어서 가져온 파일의 상태로 대출 중 사본이 있는 책을 대출 중 비율
  순서로 낸다. 기간 대출 수는 말하지 않는다.
"""

from collections import defaultdict

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.models import Book
from app.core import clock
from app.core.text import korean_order
from app.library.analytics.periods import PeriodPreset, resolve_period
from app.library.analytics.scope import FIELD, BookFilter
from app.library.models.book_request import BookRequest, BookRequestStatus
from app.library.models.catalog import Holding, HoldingStatus, LibraryBook
from app.library.models.circulation import Loan
from app.library.models.library import Library, LoanMode
from app.library.recommendation.search import recommendable_ids
from app.library.schemas.purchase_candidates import (
    FieldFigure,
    ImportedPopular,
    LoanPopular,
    PopularBasis,
    PurchaseCandidates,
    WishCandidate,
)
from app.library.services import analytics

DEFAULT_PERIOD = PeriodPreset.LAST_90_DAYS
POPULAR_LIMIT = 10
FIELD_TOP_N = 10


async def _held_isbns(session: AsyncSession, library_id: int, isbns: set[str]) -> set[str]:
    """그 기관이 지금 소장한(추천 가능한) 책의 ISBN. 공식 서지 ISBN과 기관 도서 ISBN을 모두 본다."""
    if not isbns:
        return set()
    rows = await session.execute(
        select(LibraryBook.isbn, Book.isbn)
        .select_from(LibraryBook)
        .outerjoin(Book, Book.id == LibraryBook.book_id)
        .where(
            LibraryBook.library_id == library_id,
            LibraryBook.id.in_(recommendable_ids(library_id)),
            or_(LibraryBook.isbn.in_(isbns), Book.isbn.in_(isbns)),
        )
    )
    return {isbn for pair in rows for isbn in pair if isbn is not None}


async def _wishes(session: AsyncSession, library_id: int) -> tuple[list[WishCandidate], int]:
    rows = (
        await session.execute(
            select(BookRequest.isbn, BookRequest.title, BookRequest.author)
            .where(
                BookRequest.library_id == library_id,
                BookRequest.status == BookRequestStatus.REQUESTED,
                BookRequest.isbn.is_not(None),
            )
            .order_by(BookRequest.created_at, BookRequest.id)
        )
    ).all()
    held = await _held_isbns(session, library_id, {isbn for isbn, _, _ in rows})
    first: dict[str, tuple[str, str | None]] = {}
    counts: dict[str, int] = defaultdict(int)
    for isbn, title, author in rows:  # 가장 이른 신청의 서명·저자를 쓴다
        if isbn in held:
            continue
        first.setdefault(isbn, (title, author))
        counts[isbn] += 1
    order = {isbn: n for n, isbn in enumerate(first)}  # 가장 이른 신청 순서
    wishes = [
        WishCandidate(isbn=isbn, title=first[isbn][0], author=first[isbn][1], request_count=n)
        for isbn, n in sorted(counts.items(), key=lambda kv: (-kv[1], order[kv[0]], kv[0]))
    ]
    without_isbn = await session.scalar(
        select(func.count()).where(
            BookRequest.library_id == library_id,
            BookRequest.status == BookRequestStatus.REQUESTED,
            BookRequest.isbn.is_(None),
        )
    )
    return wishes, without_isbn or 0


def _holding_counts(library_id: int):
    """책마다 제적을 뺀 사본 수, 대출 중 수, 가장 늦은 가져오기 시각."""
    return (
        select(
            Holding.library_book_id.label("book_id"),
            func.count().filter(Holding.status != HoldingStatus.WITHDRAWN).label("copies"),
            func.count().filter(Holding.status == HoldingStatus.ON_LOAN).label("on_loan"),
            func.max(Holding.last_synced_at).label("synced_at"),
        )
        .where(Holding.library_id == library_id)
        .group_by(Holding.library_book_id)
        .subquery("counts")
    )


def _shown():
    """표시 값: 공식 서지가 먼저, 없으면 기관 값."""
    return (
        func.coalesce(Book.isbn, LibraryBook.isbn).label("isbn"),
        func.coalesce(Book.title, LibraryBook.title).label("title"),
        func.coalesce(Book.author, LibraryBook.author).label("author"),
    )


async def _loan_popular(
    session: AsyncSession, library_id: int, preset: PeriodPreset
) -> list[LoanPopular]:
    period = resolve_period(preset, None, clock.today())
    counts = _holding_counts(library_id)
    loans = (
        select(Holding.library_book_id.label("book_id"), func.count().label("loans"))
        .join(Loan, (Loan.holding_id == Holding.id) & (Loan.library_id == Holding.library_id))
        .where(Holding.library_id == library_id, Loan.loaned_on.between(period.start, period.end))
        .group_by(Holding.library_book_id)
        .subquery("loan_counts")
    )
    isbn, title, author = _shown()
    rows = await session.execute(
        select(isbn, title, author, loans.c.loans, counts.c.copies, counts.c.on_loan)
        .select_from(LibraryBook)
        .outerjoin(Book, Book.id == LibraryBook.book_id)
        .join(loans, loans.c.book_id == LibraryBook.id)
        .join(counts, counts.c.book_id == LibraryBook.id)
        .where(LibraryBook.library_id == library_id, counts.c.copies >= 1, isbn.is_not(None))
        .order_by(loans.c.loans.desc(), korean_order(title), LibraryBook.id)
        .limit(POPULAR_LIMIT)
    )
    return [
        LoanPopular(isbn=i, title=t, author=a, loans=n, copies=c, on_loan=o)
        for i, t, a, n, c, o in rows
    ]


async def _imported_popular(session: AsyncSession, library_id: int) -> list[ImportedPopular]:
    counts = _holding_counts(library_id)
    isbn, title, author = _shown()
    rows = await session.execute(
        select(isbn, title, author, counts.c.copies, counts.c.on_loan, counts.c.synced_at)
        .select_from(LibraryBook)
        .outerjoin(Book, Book.id == LibraryBook.book_id)
        .join(counts, counts.c.book_id == LibraryBook.id)
        .where(
            LibraryBook.library_id == library_id,
            counts.c.copies >= 1,
            counts.c.on_loan >= 1,
            isbn.is_not(None),
        )
        # 대출 중 비율(정수 연산) → 대출 중 수 → 서명 가나다순 → id
        .order_by(
            (counts.c.on_loan * 10000 / counts.c.copies).desc(),
            counts.c.on_loan.desc(),
            korean_order(title),
            LibraryBook.id,
        )
        .limit(POPULAR_LIMIT)
    )
    return [
        ImportedPopular(isbn=i, title=t, author=a, copies=c, on_loan=o, synced_at=s)
        for i, t, a, c, o, s in rows
    ]


async def _fields(
    session: AsyncSession, library_id: int, preset: PeriodPreset | None
) -> list[FieldFigure]:
    status = await analytics.collection_status(
        session, library_id, group_by=FIELD, book_filter=BookFilter()
    )
    loans = {}
    if preset is not None:
        stats = await analytics.loan_stats(
            session,
            library_id,
            period=preset,
            month=None,
            group_by=FIELD,
            book_filter=BookFilter(),
            top_n=FIELD_TOP_N,
        )
        loans = {g.key: g for g in stats.groups}
    return [
        FieldFigure(
            field=g.label,
            titles=g.titles,
            copies=g.copies,
            loans=loans[g.key].loans if g.key in loans else None,
            loans_per_copy=loans[g.key].loans_per_copy if g.key in loans else None,
        )
        for g in status.groups
    ]


async def purchase_candidates(
    session: AsyncSession, library_id: int, period: PeriodPreset | None = None
) -> PurchaseCandidates:
    """희망도서·인기·분야 숫자. `period`는 자체 대출 기관만 쓴다(기본 최근 90일)."""
    library = await session.get(Library, library_id)
    assert library is not None
    wishes, without_isbn = await _wishes(session, library_id)
    if library.loan_mode == LoanMode.INTERNAL:
        preset = period or DEFAULT_PERIOD
        return PurchaseCandidates(
            basis=PopularBasis.LOAN_COUNT,
            period=resolve_period(preset, None, clock.today()),
            wishes=wishes,
            wishes_without_isbn=without_isbn,
            popular=await _loan_popular(session, library_id, preset),
            fields=await _fields(session, library_id, preset),
        )
    return PurchaseCandidates(
        basis=PopularBasis.IMPORTED_STATUS,
        period=None,
        wishes=wishes,
        wishes_without_isbn=without_isbn,
        popular=await _imported_popular(session, library_id),
        fields=await _fields(session, library_id, None),
    )
