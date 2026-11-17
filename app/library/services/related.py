"""관련 책: 비슷한 책과 대화 세션의 최근 기록. REST(`GET /catalog/books/{id}/similar`)와 AI 사서
tool(`find_related_books`)이 이 함수만 부른다(설계 원칙 1). LLM을 쓰지 않는다.

- 추천 실험이 정한 기본 설정(`SimilarSettings()`, `HistorySettings()`)을 그대로 쓴다. 여기서 설정을
  다시 고르지 않는다. 기본값이 바뀌면 제품도 따라간다.
- 저장된 벡터만 쓴다. 질의를 인코딩하지 않아 임베딩 서버가 없어도 돈다. 모델 이름은 설정의 임베딩
  모델이다.
- 대출 신호 공급은 없다(정보나루 테이블은 `add-loan-signal-store`). 함께 대출 신호는 비고, 인기
  채우기는 우리 도서관 인기에서 끝난다.
- 범위는 부르는 쪽 조건(`within`)과 기관 개별 기능이 등록한 조건(`hooks.related_scope_conditions`)을
  모두 건다. 질의, 실행, 노출 기록을 남기지 않는다.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.library.hooks import related_scope_conditions
from app.library.models.catalog import LibraryBook
from app.library.recommendation.basis import basis_codes, basis_texts
from app.library.recommendation.lookup import get_findable
from app.library.recommendation.ranking import Ranked
from app.library.recommendation.related import (
    HistorySettings,
    SimilarSettings,
    find_from_history,
    find_similar,
)
from app.library.recommendation.search import Candidate, get_candidates

SESSION_BOOK_LIMIT = 3  # 대화 세션의 책 중 최근 기록으로 쓰는 권수(실험의 기록은 2~3권)
SESSION_BOOKS = "session_book_ids"  # 대화가 관련 책 tool에 넘기는 실행 값의 이름


@dataclass(frozen=True)
class RelatedItem:
    candidate: Candidate
    basis: tuple[str, ...]  # 근거 코드(오른 신호 이름) 모두
    basis_text: tuple[str, ...]  # 근거 문구, 두 개까지


async def _scope(
    session: AsyncSession, library_id: int, base_ids: Sequence[int], within: Select | None
) -> Select | None:
    conditions = [] if within is None else [within]
    conditions += await related_scope_conditions(session, library_id, base_ids)
    if not conditions:
        return None
    query = select(LibraryBook.id).where(LibraryBook.library_id == library_id)
    for condition in conditions:
        query = query.where(LibraryBook.id.in_(condition))
    return query


async def _items(
    session: AsyncSession, library_id: int, ranked: Sequence[Ranked], *, history: bool
) -> list[RelatedItem]:
    candidates = await get_candidates(session, library_id, [r.library_book_id for r in ranked])
    items = []
    for result in ranked:
        candidate = candidates.get(result.library_book_id)
        if candidate is None:
            continue
        kdc = candidate.library_book.shown("kdc")
        items.append(
            RelatedItem(
                candidate,
                tuple(basis_codes(result.ranks)),
                tuple(basis_texts(result.ranks, kdc=kdc, history=history)),
            )
        )
    return items


async def similar_for_book(
    session: AsyncSession,
    library_id: int,
    library_book_id: int,
    *,
    within: Select | None = None,
) -> list[RelatedItem]:
    """기준 책과 비슷한, 그 기관의 추천 가능한 책.

    기준 책이 그 기관의 찾을 수 있는 책이 아니면 NotFoundError다.
    """
    await get_findable(session, library_id, library_book_id)
    ranked = await find_similar(
        session,
        get_settings().embedding_model,
        library_id=library_id,
        library_book_id=library_book_id,
        within=await _scope(session, library_id, [library_book_id], within),
        settings=SimilarSettings(),
        loan_signals=None,
    )
    return await _items(session, library_id, ranked, history=False)


async def related_for_session(
    session: AsyncSession,
    library_id: int,
    session_book_ids: Sequence[int],
    *,
    within: Select | None = None,
) -> list[RelatedItem]:
    """대화 세션의 책(최신 순)을 기록으로 한 추천.

    책이 없으면 우리 도서관 인기이고, 그것도 비면 빈 결과다.

    그 기관에서 지금 추천할 수 없는 책(다른 기관의 책, 제적 사본만 남은 책)은 기록에서 건너뛴다.
    """
    wanted = list(dict.fromkeys(session_book_ids))
    candidates = await get_candidates(session, library_id, wanted)
    bases = [i for i in wanted if i in candidates and candidates[i].recommendable]
    bases = bases[:SESSION_BOOK_LIMIT]
    ranked = await find_from_history(
        session,
        get_settings().embedding_model,
        library_id=library_id,
        library_book_ids=bases,
        within=await _scope(session, library_id, bases, within),
        settings=HistorySettings(),
        loan_signals=None,
    )
    return await _items(session, library_id, ranked, history=True)
