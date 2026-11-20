"""연체 안내 tool: 운영 에이전트의 `list_overdue_loans`(조회)와 `draft_overdue_notice`(쓰기).

두 tool 모두 연체 안내 REST와 같은 service(`services/overdue_notices.py`)를 부른다. 기관은 실행기가
정한다. 회원 값(이름, 회원번호, 전화번호)은 LLM에 보내지 않는다: 연체 목록은 결과 모델
(`OverdueLoanList`)의 필드만 내고, 안내문 틀 초안은 채운 문안을 돌려주지 않는다. 두 tool 모두
입력을 실행 기록에 남기지 않는다(틀 문장은 틀 행에만 저장된다).

외부 대출 기관 프로필에는 두 tool을 넣지 않는다. service도 409로 막는다.
"""

from typing import Any

from pydantic import ConfigDict, Field, ValidationError

from app.agent.tools import Tool, ToolContext, ToolInput
from app.core.errors import InvalidRequestError
from app.library.models.overdue_notice import BODY_LIMIT
from app.library.overdue_template import PLACEHOLDERS, REQUIRED
from app.library.schemas.overdue_notice import OverdueLoanItem, OverdueLoanList, TemplateWrite
from app.library.services import overdue_notices as svc

LIST_LIMIT = 20


class NoInput(ToolInput):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"required": []})


class DraftOverdueNoticeInput(ToolInput):
    template: str = Field(
        description=(
            f"연체 안내문 틀 한 문장({BODY_LIMIT}자 이내). 회원 값은 자리표시로만 쓴다. 쓸 수 있는 "
            f"자리표시: {' '.join(PLACEHOLDERS)}. {' '.join(REQUIRED)}는 꼭 넣는다. 회원 이름, "
            "회원번호, 전화번호, 날짜, 책 제목을 직접 쓰지 않는다"
        )
    )


async def _list(ctx: ToolContext, data: NoInput) -> dict[str, Any]:
    loans = await svc.overdue_loans(ctx.session, ctx.library_id)
    template = await svc.current_template(ctx.session, ctx.library_id)
    shown = loans[:LIST_LIMIT]
    result = OverdueLoanList(
        total=len(loans),
        shown=len(shown),
        truncated=len(loans) > len(shown),
        has_template=template is not None,
        items=[
            OverdueLoanItem(
                title=loan.title,
                accession_number=loan.accession_number,
                due_on=loan.due_on,
                overdue_days=loan.overdue_days,
            )
            for loan in shown
        ],
    )
    return result.model_dump(mode="json")


def _write(data: DraftOverdueNoticeInput) -> TemplateWrite:
    try:
        return TemplateWrite(body=data.template)
    except ValidationError as exc:
        problems = "; ".join(e["msg"] for e in exc.errors())
        raise InvalidRequestError(f"안내문 틀 규칙에 맞지 않습니다: {problems}") from exc


async def _draft(ctx: ToolContext, data: DraftOverdueNoticeInput) -> dict[str, Any]:
    template = await svc.create_template(
        ctx.session, ctx.library_id, None, _write(data), submit=True
    )
    loans = await svc.overdue_loans(ctx.session, ctx.library_id)
    return {
        "template_id": template.id,
        "status": template.status.value,
        "overdue_count": len(loans),
        "note": (
            "승인 대기로 올렸다. 관리자가 승인하면 이 틀로 연체 안내 목록이 만들어진다고 알린다. "
            "채운 문안과 회원 정보는 관리 화면의 연체 안내 목록에서만 볼 수 있다."
        ),
    }


LIST_OVERDUE_LOANS = Tool(
    "list_overdue_loans",
    "지금 연체 중인 대출(반납 예정일이 지났고 반납하지 않음)을 본다. 책마다 서명, 등록번호, 반납 "
    f"예정일, 연체 일수가 있고 {LIST_LIMIT}건까지다. 누가 빌렸는지는 알려 주지 않는다. "
    "has_template은 확정된 연체 안내문 틀이 있는지다. 입력이 없다.",
    NoInput,
    _list,
    "연체 목록을 보고 있어요",
)

DRAFT_OVERDUE_NOTICE = Tool(
    "draft_overdue_notice",
    "연체 안내문 틀(자리표시가 든 문장 하나)을 만들어 승인 대기로 올린다. 승인·확정은 하지 않는다. "
    "회원별 문안은 승인 뒤 코드가 채운다.",
    DraftOverdueNoticeInput,
    _draft,
    "연체 안내문 틀을 만들고 있어요",
)
