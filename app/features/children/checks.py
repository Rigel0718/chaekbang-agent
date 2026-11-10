"""어린이 최종 검사. 어린이 요청의 답에는 그 기관의 어린이 도서만 있어야 한다.

어린이 요청 판단은 코드가 한다. 이용자 문장의 규칙(`rules.is_children_request`)이 어린이 요청이라고
보거나, 이번 실행에서 어린이 도서 검색 tool을 썼으면 어린이 요청이다.
LLM의 신호는 켜는 쪽으로만 쓴다.
분류 행이 없는 책은 일반 도서다.
"""

from typing import Any

from app.agent.profile import CheckContext, Violation
from app.features.children.models import LibraryBookAudience
from app.features.children.rules import is_children_request
from app.features.children.service import children_book_ids
from app.library.recommendation.checks import recommended_ids

CHILDREN_TOOL_NAME = "search_children_books"
CHILDREN_VIOLATION = (
    "어린이 요청입니다. 다음 library_book_id는 이 도서관의 어린이 도서가 아닙니다: {ids}. "
    "search_children_books 결과에 나온 책으로만 다시 답하세요."
)


def is_children_run(ctx: CheckContext) -> bool:
    return is_children_request(ctx.user_texts) or CHILDREN_TOOL_NAME in ctx.tool_names


class ChildrenCheck:
    name = "children"

    async def check(self, ctx: CheckContext, answer: Any) -> list[Violation]:
        ids = recommended_ids(answer)
        if not ids or not is_children_run(ctx):
            return []
        children = set(
            await ctx.session.scalars(
                children_book_ids(ctx.library_id).where(
                    LibraryBookAudience.library_book_id.in_(ids)
                )
            )
        )
        wrong = tuple(dict.fromkeys(i for i in ids if i not in children))
        if not wrong:
            return []
        return [Violation(CHILDREN_VIOLATION.format(ids=", ".join(map(str, wrong))), wrong)]
