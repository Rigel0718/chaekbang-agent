"""서명·저자 찾기, 자동완성, 비슷한 책 API. 키오스크와 관리자가 쓴다.

LLM을 부르지 않고 질의를 저장하지 않는다.
"""

from typing import Annotated

from fastapi import APIRouter, Query

from app.library.api.librarian import QueryEncoder
from app.library.deps import CurrentStaff, Session
from app.library.recommendation.cards import build_summaries
from app.library.recommendation.lookup import find_books, suggest_books
from app.library.schemas.catalog import BookSuggestion, BookSummary, RelatedBook
from app.library.services.related import similar_for_book
from app.library.services.topic import search_topic_text

router = APIRouter(prefix="/catalog", tags=["catalog"])

MAX_QUERY_LENGTH = 100
QueryText = Annotated[str, Query(min_length=1, max_length=MAX_QUERY_LENGTH)]


@router.get("/search")
async def search(q: QueryText, staff: CurrentStaff, session: Session) -> list[BookSummary]:
    """서명·저자로 찾는다. 공백·대소문자·한 글자 안팎의 오타를 허용한다. 최대 10권이다."""
    found = await find_books(session, staff.library_id, q)
    return await build_summaries(session, staff.library_id, [f.candidate for f in found])


@router.get("/topic")
async def topic(
    q: QueryText, staff: CurrentStaff, session: Session, encoder: QueryEncoder
) -> list[BookSummary]:
    """질의를 낱말로 나눠 주제로 찾는다(AI 사서의 소장 도서 검색과 같은 제품 경로). 최대 10권이다.

    키워드와 벡터 순위를 합친다. 임베딩 서버가 없거나 실패하면 키워드 순위로 내려가고 결과
    모양은 같다. 낱말이 없으면 빈 목록이다. LLM을 부르지 않고 질의와 기록을 남기지 않는다.
    """
    found = await search_topic_text(session, staff.library_id, q, encoder=encoder)
    return await build_summaries(session, staff.library_id, found.candidates)


@router.get("/suggest")
async def suggest(q: QueryText, staff: CurrentStaff, session: Session) -> list[BookSuggestion]:
    """입력 중인 글자(조합 중 자모 포함)로 서명·저자 후보를 돌려준다. 최대 8개다."""
    found = await suggest_books(session, staff.library_id, q)
    return [
        BookSuggestion(library_book_id=s.library_book_id, title=s.title, author=s.author)
        for s in found
    ]


@router.get("/books/{library_book_id}/similar")
async def similar(library_book_id: int, staff: CurrentStaff, session: Session) -> list[RelatedBook]:
    """찾은 책 카드 아래 비슷한 책. 최대 5권이고 책마다 근거(코드와 문구)가 있다.

    기준 책이 이 기관의 찾을 수 있는 책이 아니면 404다. 임베딩 서버를 부르지 않는다.
    """
    items = await similar_for_book(session, staff.library_id, library_book_id)
    summaries = await build_summaries(session, staff.library_id, [i.candidate for i in items])
    return [
        RelatedBook(
            **summary.model_dump(), basis=list(item.basis), basis_text=list(item.basis_text)
        )
        for summary, item in zip(summaries, items, strict=True)
    ]
