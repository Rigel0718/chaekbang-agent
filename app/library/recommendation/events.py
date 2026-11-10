"""추천 노출 기록. 검사를 통과해 이용자에게 보인 추천만 남긴다.

기관, 기관 도서, 실행, 순서, 노출 시점의 대출 가능 여부, 시각만 둔다. 회원, 세션, 문장, 이유, 어린이
구분은 두지 않는다. 전환은 조회할 때 계산한다.
"""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.library.models.chat import RecommendationEvent
from app.library.schemas.librarian import BookCard


def add_events(
    session: AsyncSession, library_id: int, run_id: int, cards: Sequence[BookCard]
) -> None:
    """카드 순서대로 1부터 기록한다. 커밋은 부르는 쪽이 한다."""
    shown_at = clock.now()
    session.add_all(
        RecommendationEvent(
            library_id=library_id,
            library_book_id=card.library_book_id,
            run_id=run_id,
            position=position,
            was_available=card.available_count > 0,
            shown_at=shown_at,
        )
        for position, card in enumerate(cards, start=1)
    )
