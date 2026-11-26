"""구매 요청서 tool: 운영 에이전트의 `list_purchase_candidates`, `draft_purchase_request`.

두 tool 모두 구매 후보 REST·요청서 REST와 같은 service(`services/purchase_candidates.py`,
`services/purchase_requests.py`)를 부른다. 기관은 실행기가 정한다. 두 운영 방식 프로필에 모두 있다.

- 회원 값은 LLM에 가지 않는다. 후보 결과는 허용 목록 필드(`PurchaseCandidates`)뿐이고 희망도서는
  신청 건수만 있다.
- 금액은 LLM에 가지 않는다. 두 tool 모두 정가를 조회하지 않고 결과에 가격이 없다. 금액은 관리
  화면의 상세에서 YES24 정가로 계산되고 승인할 때 기록된다.
- LLM이 책을 지어낼 길이 없다. 초안의 ISBN은 그때 다시 계산한 후보(희망도서·인기)에 있어야 하고,
  서명·저자·근거 종류는 코드가 후보에서 채운다(둘 다면 희망도서). 부족 분야(`field_gap`)·직접
  입력(`manual`) 항목은 관리자가 REST로만 넣는다.
"""

from typing import Any

from pydantic import Field, ValidationError

from app.agent.tools import Tool, ToolContext, ToolInput
from app.core.errors import InvalidRequestError
from app.core.isbn import InvalidIsbnError, normalize_isbn
from app.library.analytics.periods import PeriodPreset
from app.library.models.purchase_request import (
    ITEM_AUTHOR_LIMIT,
    ITEM_TITLE_LIMIT,
    MAX_ITEMS,
    MAX_QUANTITY,
    MIN_QUANTITY,
    NOTE_LIMIT,
    REASON_LIMIT,
    TITLE_LIMIT,
    ReasonKind,
)
from app.library.schemas.admin_results import DraftLink
from app.library.schemas.purchase_request import PurchaseRequestWrite
from app.library.services import purchase_candidates as candidates_svc
from app.library.services import purchase_requests as svc

PERIOD_DESCRIPTION = (
    "자체 대출 기관의 인기 후보를 셀 기간 프리셋. 말하지 않았으면 null(기본 기간). 답에서 기간은 "
    "결과의 period.label로 말한다. 외부 대출 기관에서는 쓰지 않는다"
)


class CandidatesInput(ToolInput):
    period: PeriodPreset | None = Field(description=PERIOD_DESCRIPTION)


class DraftItem(ToolInput):
    isbn: str = Field(description="list_purchase_candidates 결과(wishes 또는 popular)의 ISBN")
    quantity: int = Field(
        ge=MIN_QUANTITY, le=MAX_QUANTITY, description=f"살 권수 {MIN_QUANTITY}~{MAX_QUANTITY}"
    )
    reason: str | None = Field(
        description=f"근거 한 줄({REASON_LIMIT}자 이내). 후보 결과의 숫자에만 근거한다. 없으면 null"
    )


class DraftPurchaseInput(ToolInput):
    title: str = Field(description=f"요청서 제목. {TITLE_LIMIT}자 이내")
    note: str | None = Field(description=f"메모({NOTE_LIMIT}자 이내). 없으면 null")
    period: PeriodPreset | None = Field(
        description="후보를 볼 때 쓴 기간 프리셋(list_purchase_candidates와 같은 값). 없으면 null"
    )
    items: list[DraftItem] = Field(description=f"살 책. 서로 다른 ISBN, 1~{MAX_ITEMS}개")


async def _candidates(ctx: ToolContext, data: CandidatesInput) -> dict[str, Any]:
    result = await candidates_svc.purchase_candidates(ctx.session, ctx.library_id, data.period)
    return result.model_dump(mode="json")


def _isbn(raw: str) -> str | None:
    try:
        return normalize_isbn(raw)
    except InvalidIsbnError:
        return None


async def _write(ctx: ToolContext, data: DraftPurchaseInput) -> PurchaseRequestWrite:
    found = await candidates_svc.purchase_candidates(ctx.session, ctx.library_id, data.period)
    wishes = {w.isbn: w for w in found.wishes}
    popular = {p.isbn: p for p in found.popular}
    items: list[dict[str, Any]] = []
    unknown: list[str] = []
    for item in data.items:
        isbn = _isbn(item.isbn)
        source = (wishes.get(isbn) or popular.get(isbn)) if isbn else None
        if isbn is None or source is None:
            unknown.append(item.isbn)
            continue
        items.append(
            {
                "isbn": isbn,
                "title": source.title[:ITEM_TITLE_LIMIT],
                "author": source.author[:ITEM_AUTHOR_LIMIT] if source.author else None,
                "quantity": item.quantity,
                "reason_kind": ReasonKind.BOOK_REQUEST if isbn in wishes else ReasonKind.POPULAR,
                "reason": item.reason,
            }
        )
    if unknown:
        raise InvalidRequestError(
            "구매 후보에 없는 ISBN이 있습니다: "
            f"{', '.join(unknown)}. list_purchase_candidates 결과의 ISBN만 넣으세요"
        )
    try:
        return PurchaseRequestWrite(title=data.title, note=data.note, items=items)
    except ValidationError as exc:
        problems = "; ".join(e["msg"] for e in exc.errors())
        raise InvalidRequestError(f"구매 요청서 규칙에 맞지 않습니다: {problems}") from exc


async def _draft(ctx: ToolContext, data: DraftPurchaseInput) -> dict[str, Any]:
    request = await svc.create_request(
        ctx.session, ctx.library_id, None, await _write(ctx, data), submit=True
    )
    return {
        "purchase_request_id": request.id,
        "status": request.status.value,
        "item_count": len(request.items),
        "note": (
            "승인 대기로 올렸다. 금액은 관리 화면의 요청서 상세에서 YES24 정가로 계산되고 "
            "승인할 때 기록된다고 알린다. 금액이나 예산 숫자를 말하지 않는다."
        ),
    }


def present_draft(data: DraftPurchaseInput, output: dict[str, Any]) -> DraftLink:
    """화면용: 요청서의 종류와 id만. 항목과 안내 문구는 싣지 않는다."""
    return DraftLink(draft="purchase", id=output["purchase_request_id"])


LIST_PURCHASE_CANDIDATES = Tool(
    "list_purchase_candidates",
    "보충 구매 후보를 본다. wishes는 처리 전 희망도서(ISBN별, request_count는 신청 건수), "
    "wishes_without_isbn은 ISBN이 없어 후보에서 뺀 신청 건수, popular는 많이 빌리는 책(basis가 "
    "loan_count면 기간 대출 수, imported_status면 가져온 파일 기준 대출 중 상태와 synced_at), "
    "fields는 분야별 권수와 권당 대출이다. 누가 신청했는지와 가격은 없다.",
    CandidatesInput,
    _candidates,
    "구매 후보를 보고 있어요",
    record_fields=("period",),
)

DRAFT_PURCHASE_REQUEST = Tool(
    "draft_purchase_request",
    "보충 구매 요청서 초안을 만들어 승인 대기로 올린다. 승인·확정은 하지 않는다. 책은 먼저 "
    "list_purchase_candidates로 본 후보의 ISBN에서 고른다. 서명과 근거 종류는 코드가 채운다. "
    "결과에 금액은 없다.",
    DraftPurchaseInput,
    _draft,
    "구매 요청서 초안을 만들고 있어요",
    record_fields=("items",),
    present=present_draft,
)
