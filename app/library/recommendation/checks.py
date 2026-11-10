"""소장 검사: 답의 모든 추천은 그 기관의 추천 가능한 책이어야 한다. LLM 선택과 상관없이 돈다."""

from typing import Any

from sqlalchemy import select

from app.agent.profile import CheckContext, Violation
from app.library.models.catalog import LibraryBook
from app.library.recommendation.search import recommendable_ids

HOLDING_VIOLATION = (
    "다음 library_book_id는 이 도서관에서 지금 추천할 수 있는 책이 아닙니다: {ids}. "
    "검색 결과에 나온 책으로만 다시 답하세요."
)


def recommended_ids(answer: Any) -> list[int]:
    return [r.library_book_id for r in answer.recommendations]


class HoldingCheck:
    name = "holdings"

    async def check(self, ctx: CheckContext, answer: Any) -> list[Violation]:
        ids = recommended_ids(answer)
        if not ids:
            return []
        allowed = set(
            await ctx.session.scalars(
                select(LibraryBook.id).where(
                    LibraryBook.library_id == ctx.library_id,
                    LibraryBook.id.in_(ids),
                    LibraryBook.id.in_(recommendable_ids(ctx.library_id)),
                )
            )
        )
        wrong = tuple(dict.fromkeys(i for i in ids if i not in allowed))
        if not wrong:
            return []
        return [Violation(HOLDING_VIOLATION.format(ids=", ".join(map(str, wrong))), wrong)]
