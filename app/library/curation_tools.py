"""큐레이션 tool: 운영 에이전트의 `draft_curation`(쓰기), AI 사서의 `get_curations`(조회).

두 tool 모두 큐레이션 관리 REST와 같은 service(`services/curations.py`)를 부른다. 기관은 실행기가
정한다.

`draft_curation`은 초안을 만들고 같은 트랜잭션에서 승인 대기로 올린다. 승인·게시 tool은 없다(승인은
관리자가 REST에서 한다). 실행기의 입력 기록은 맨 위 필드만 고르므로 책 id와 이유를 나눠 받고,
책 id만 기록한다. 제목·소개·이유는 실행 기록에 남지 않고 큐레이션 행에만 저장된다.
"""

from typing import Any

from pydantic import ConfigDict, Field, ValidationError

from app.agent.tools import Tool, ToolContext, ToolInput
from app.core.errors import InvalidRequestError
from app.library.models.curation import (
    INTRO_LIMIT,
    MAX_ITEMS,
    MIN_ITEMS,
    REASON_LIMIT,
    TITLE_LIMIT,
)
from app.library.recommendation.cards import shelf_of
from app.library.recommendation.search import get_candidates
from app.library.schemas.admin_results import DraftLink
from app.library.schemas.curation import CurationWrite
from app.library.services import curations as svc
from app.library.tools import NO_SHELF, search_result

NO_CURATION = (
    "게시된 큐레이션이 없다. 큐레이션이 없다고 말하고 지어내지 않는다. 원하는 주제를 물어 "
    "search_collection으로 추천한다."
)


class DraftCurationInput(ToolInput):
    title: str = Field(description=f"큐레이션 제목. {TITLE_LIMIT}자 이내")
    intro: str | None = Field(description=f"한두 문장 소개. {INTRO_LIMIT}자 이내, 없으면 null")
    library_book_ids: list[int] = Field(
        description=(
            f"담을 책의 library_book_id. 이번 대화의 search_collection 결과에 나온 책만, "
            f"서로 다른 {MIN_ITEMS}~{MAX_ITEMS}권"
        )
    )
    reasons: list[str] = Field(
        description=(
            f"책마다 담은 이유 한 줄({REASON_LIMIT}자 이내). library_book_ids와 같은 순서, 같은 "
            "개수. 검색 결과의 서명·분류·소개에만 근거한다"
        )
    )


class NoInput(ToolInput):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"required": []})


def _write(data: DraftCurationInput) -> CurationWrite:
    if len(data.library_book_ids) != len(data.reasons):
        raise InvalidRequestError("library_book_ids와 reasons의 개수가 같아야 합니다")
    try:
        return CurationWrite(
            title=data.title,
            intro=data.intro,
            items=[
                {"library_book_id": i, "reason": r}
                for i, r in zip(data.library_book_ids, data.reasons, strict=True)
            ],
        )
    except ValidationError as exc:
        problems = "; ".join(e["msg"] for e in exc.errors())
        raise InvalidRequestError(f"큐레이션 내용 규칙에 맞지 않습니다: {problems}") from exc


async def _draft(ctx: ToolContext, data: DraftCurationInput) -> dict[str, Any]:
    curation = await svc.create_curation(
        ctx.session, ctx.library_id, None, _write(data), submit=True
    )
    return {
        "curation_id": curation.id,
        "status": curation.status.value,
        "book_count": len(curation.items),
        "note": "승인 대기로 올렸다. 관리자가 승인해야 이용자 화면에 게시된다고 알린다.",
    }


def present_draft(data: DraftCurationInput, output: dict[str, Any]) -> DraftLink:
    """화면용: 초안의 종류와 id만. 제목·소개·이유·안내 문구는 싣지 않는다."""
    return DraftLink(draft="curation", id=output["curation_id"])


DRAFT_CURATION = Tool(
    "draft_curation",
    "주제 큐레이션 초안을 만들어 승인 대기로 올린다. 승인·게시는 하지 않는다. 책은 먼저 "
    "search_collection으로 찾은 결과에서 고른다.",
    DraftCurationInput,
    _draft,
    "큐레이션 초안을 만들고 있어요",
    record_fields=("library_book_ids",),
    present=present_draft,
)


async def _curations(ctx: ToolContext, data: NoInput) -> dict[str, Any]:
    published = await svc.published_curations(ctx.session, ctx.library_id)
    ids = [b.library_book_id for p in published for b in p.books]
    candidates = await get_candidates(ctx.session, ctx.library_id, ids)
    shelf = await shelf_of(ctx.session, ctx.library_id, ids)
    curations = [
        {
            "title": p.curation.title,
            "intro": p.curation.intro,
            "books": [
                {
                    **search_result(
                        candidates[b.library_book_id], shelf.get(b.library_book_id, NO_SHELF)
                    ),
                    "reason": b.reason,
                }
                for b in p.books
            ],
        }
        for p in published
    ]
    return {"curations": curations, "note": None if curations else NO_CURATION}


GET_CURATIONS = Tool(
    "get_curations",
    "도서관이 게시한 큐레이션(이달의 추천, 주제별 추천 목록)을 최신 5개까지 본다. 책마다 "
    "담당자가 쓴 이유(reason)가 있다. 입력이 없다.",
    NoInput,
    _curations,
    "도서관 추천 목록을 보고 있어요",
)
