"""소장 도서 후보 검색. 추천 가능 조건을 한곳에 두고 검색과 소장 검사가 함께 쓴다.

표시 값은 공식 서지를 먼저 쓴다(`coalesce(Book.x, LibraryBook.x)`). 비교는 양쪽의 공백을 모두 지운
부분 문자열이다. 한국어는 조사가 붙고 띄어쓰기 표기가 자주 달라서다. 저자는 구조화하지 않고 원문을
그대로 찾는다.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import ColumnElement, Select, case, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.models import Book
from app.core.tenancy import get_owned
from app.library.models.catalog import Holding, HoldingStatus, LibraryBook
from app.library.models.library import Library, LoanMode

LABEL = "도서"
SEARCH_LIMIT = 10
RECOMMENDABLE_STATUSES = (HoldingStatus.AVAILABLE, HoldingStatus.ON_LOAN)

# 키워드가 맞은 위치의 가중치. 값은 평가에서 조정한다.
WEIGHTS: tuple[tuple[str, int], ...] = (
    ("title", 4),
    ("subtitle", 3),
    ("series_name", 3),
    ("author", 3),
    ("description", 1),
)
OFFICIAL_ONLY = {"subtitle", "series_name"}


@dataclass(frozen=True)
class Candidate:
    library_book: LibraryBook
    available_count: int
    on_loan_count: int
    status_synced_at: datetime | None  # 가져오기 기관만. 사본 중 가장 오래된 갱신 시각

    @property
    def recommendable(self) -> bool:
        return self.available_count + self.on_loan_count > 0


def recommendable_ids(library_id: int) -> Select:
    """대출 가능이나 대출 중 사본이 하나 이상 있는 그 기관의 기관 도서 id."""
    return (
        select(Holding.library_book_id)
        .where(Holding.library_id == library_id, Holding.status.in_(RECOMMENDABLE_STATUSES))
        .distinct()
    )


def _squash(expr: ColumnElement) -> ColumnElement:
    return func.regexp_replace(func.coalesce(expr, ""), r"\s", "", "g")


def _squash_text(value: str) -> str:
    return "".join(value.split())


def _pattern(keyword: str) -> str:
    escaped = keyword.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _shown(field: str) -> ColumnElement:
    if field in OFFICIAL_ONLY:
        return getattr(Book, field)
    return func.coalesce(getattr(Book, field), getattr(LibraryBook, field))


def _score(keywords: Sequence[str]) -> ColumnElement:
    terms: list[ColumnElement] = []
    for keyword in keywords:
        pattern = _pattern(keyword)
        for field, weight in WEIGHTS:
            matched = _squash(_shown(field)).ilike(pattern, escape="\\")
            terms.append(case((matched, weight), else_=0))
    total: ColumnElement = literal(0)
    for term in terms:
        total = total + term
    return total


def _counts(library_id: int):
    synced_missing = func.bool_or(Holding.last_synced_at.is_(None))
    return (
        select(
            Holding.library_book_id,
            func.count().filter(Holding.status == HoldingStatus.AVAILABLE).label("available"),
            func.count().filter(Holding.status == HoldingStatus.ON_LOAN).label("on_loan"),
            case((synced_missing, None), else_=func.min(Holding.last_synced_at)).label("synced"),
        )
        .where(Holding.library_id == library_id, Holding.status.in_(RECOMMENDABLE_STATUSES))
        .group_by(Holding.library_book_id)
        .subquery()
    )


async def _loan_mode(session: AsyncSession, library_id: int) -> LoanMode:
    mode = await session.scalar(select(Library.loan_mode).where(Library.id == library_id))
    assert mode is not None
    return mode


def clean_keywords(keywords: Sequence[str]) -> list[str]:
    """공백을 지우고 빈 값과 중복을 뺀다."""
    seen: list[str] = []
    for keyword in keywords:
        squashed = _squash_text(keyword)
        if squashed and squashed.casefold() not in {k.casefold() for k in seen}:
            seen.append(squashed)
    return seen


async def search_collection(
    session: AsyncSession,
    library_id: int,
    keywords: Sequence[str],
    *,
    within: Select | None = None,
    limit: int = SEARCH_LIMIT,
) -> list[Candidate]:
    """추천 가능한 책 중 키워드 하나라도 맞는 책. 키워드가 없으면 둘러보기다.

    within은 기관 개별 기능이 넘기는 기관 도서 id 조건이다. 공통은 그 뜻을 모른다.
    """
    words = clean_keywords(keywords)
    counts = _counts(library_id)
    score = _score(words) if words else literal(0)
    query = (
        select(LibraryBook, counts.c.available, counts.c.on_loan, counts.c.synced)
        .join(counts, counts.c.library_book_id == LibraryBook.id)
        .outerjoin(Book, Book.id == LibraryBook.book_id)
        .where(LibraryBook.library_id == library_id)
    )
    if within is not None:
        query = query.where(LibraryBook.id.in_(within))
    if words:
        query = query.where(score > 0)
    query = query.order_by(
        score.desc(),
        (counts.c.available > 0).desc(),
        func.coalesce(Book.title, LibraryBook.title),
        LibraryBook.id,
    ).limit(min(limit, SEARCH_LIMIT))
    imported = await _loan_mode(session, library_id) == LoanMode.IMPORTED
    rows = await session.execute(query)
    return [
        Candidate(book, available, on_loan, synced if imported else None)
        for book, available, on_loan, synced in rows.unique()
    ]


async def get_candidates(
    session: AsyncSession, library_id: int, library_book_ids: Sequence[int]
) -> dict[int, Candidate]:
    """그 기관의 기관 도서를 사본 수와 함께. 사본이 없거나 추천할 수 없어도 돌려준다."""
    if not library_book_ids:
        return {}
    counts = _counts(library_id)
    rows = await session.execute(
        select(LibraryBook, counts.c.available, counts.c.on_loan, counts.c.synced)
        .outerjoin(counts, counts.c.library_book_id == LibraryBook.id)
        .where(LibraryBook.library_id == library_id, LibraryBook.id.in_(library_book_ids))
    )
    imported = await _loan_mode(session, library_id) == LoanMode.IMPORTED
    return {
        book.id: Candidate(book, available or 0, on_loan or 0, synced if imported else None)
        for book, available, on_loan, synced in rows.unique()
    }


async def get_candidate(session: AsyncSession, library_id: int, library_book_id: int) -> Candidate:
    """다른 기관의 책은 NotFoundError다."""
    await get_owned(session, LibraryBook, library_id, library_book_id, label=LABEL)
    return (await get_candidates(session, library_id, [library_book_id]))[library_book_id]
