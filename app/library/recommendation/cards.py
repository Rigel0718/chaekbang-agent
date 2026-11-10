"""추천 카드. 서지와 사본 정보는 코드가 DB 값으로 채우고, LLM에서는 이유만 받는다."""

from collections.abc import Sequence
from typing import Any

from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.models import ExternalSource
from app.library.models.catalog import Holding, HoldingStatus
from app.library.recommendation.search import RECOMMENDABLE_STATUSES, Candidate, get_candidates
from app.library.schemas.catalog import BookSummary
from app.library.schemas.librarian import BookCard

COVER_SOURCES = {ExternalSource.YES24: "YES24"}


def unique_recommendations(answer: Any) -> list[Any]:
    """같은 책이 두 번 있으면 처음 것만 둔다."""
    seen: set[int] = set()
    kept = []
    for item in answer.recommendations:
        if item.library_book_id not in seen:
            seen.add(item.library_book_id)
            kept.append(item)
    return kept


async def _shelf(
    session: AsyncSession, library_id: int, ids: Sequence[int]
) -> dict[int, tuple[str | None, str | None]]:
    """책마다 대출 가능한 사본을 먼저 고른 서가 위치와 청구기호."""
    rows = await session.execute(
        select(Holding.library_book_id, Holding.shelf_location, Holding.call_number)
        .where(
            Holding.library_id == library_id,
            Holding.library_book_id.in_(ids),
            Holding.status.in_(RECOMMENDABLE_STATUSES),
        )
        .order_by(
            Holding.library_book_id,
            case((Holding.status == HoldingStatus.AVAILABLE, 0), else_=1),
            Holding.accession_number,
        )
    )
    shelf: dict[int, tuple[str | None, str | None]] = {}
    for book_id, location, call_number in rows:
        shelf.setdefault(book_id, (location, call_number))
    return shelf


def _summary(candidate: Candidate, shelf: tuple[str | None, str | None]) -> dict[str, Any]:
    book = candidate.library_book
    official = book.book
    return {
        "library_book_id": book.id,
        "title": book.shown("title"),
        "author": book.shown("author"),
        "publisher": book.shown("publisher"),
        "available_count": candidate.available_count,
        "on_loan_count": candidate.on_loan_count,
        "shelf_location": shelf[0],
        "call_number": shelf[1],
        "cover_url": book.shown("cover_url"),
        "cover_source": COVER_SOURCES.get(official.external_source)
        if official is not None and official.external_source is not None
        else None,
        "product_url": official.external_url if official is not None else None,
        "status_synced_at": candidate.status_synced_at,
    }


async def build_summaries(
    session: AsyncSession, library_id: int, candidates: Sequence[Candidate]
) -> list[BookSummary]:
    """찾기 결과의 요약. 카드와 같은 서지·대출 상태이고 추천 이유는 없다."""
    shelf = await _shelf(session, library_id, [c.library_book.id for c in candidates])
    return [
        BookSummary(**_summary(c, shelf.get(c.library_book.id, (None, None)))) for c in candidates
    ]


async def build_cards(session: AsyncSession, library_id: int, answer: Any) -> list[BookCard]:
    """검사를 통과한 답의 추천을 카드로 만든다. 그 기관의 책만 카드가 된다."""
    items = unique_recommendations(answer)
    ids = [item.library_book_id for item in items]
    candidates = await get_candidates(session, library_id, ids)
    shelf = await _shelf(session, library_id, ids)
    return [
        BookCard(
            **_summary(
                candidates[item.library_book_id], shelf.get(item.library_book_id, (None, None))
            ),
            reason=item.reason,
        )
        for item in items
        if item.library_book_id in candidates
    ]
