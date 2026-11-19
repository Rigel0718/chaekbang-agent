"""운영 에이전트의 분석 tool 네 개. service(`services/analytics.py`)를 감싸고 기관은 실행기가
주입한다.

입력 모델은 조립 때 만든다. 등록된 분석 축의 이름이 묶기 값과 필터 필드가 되고, 축이 없으면 그
필드 자체가 없다. LLM이 정하는 값은 enum과 상한 있는 정수뿐이다. 날짜는 코드가 계산한다.

입력은 모두 실행 기록에 남긴다(enum과 정수라 이용자 문장이 섞이지 않는다). 평가는 이 기록으로
tool 선택을 판정한다. 결과는 service 스키마를 그대로 JSON으로 낸다.
"""

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import Field, create_model

from app.agent.tools import Tool, ToolContext, ToolInput
from app.library.analytics.axes import AnalysisAxis
from app.library.analytics.fields import Field as BookField
from app.library.analytics.periods import PeriodPreset
from app.library.analytics.scope import ACQUISITION, FIELD, STATUS, BookFilter
from app.library.models.catalog import HoldingStatus
from app.library.schemas.analytics import LIMIT_MAX, TOP_N_MAX
from app.library.services import analytics

GET_COLLECTION_STATUS = "get_collection_status"
LIST_HOLDINGS_BY_STATUS = "list_holdings_by_status"
GET_LOAN_STATS = "get_loan_stats"
LIST_UNBORROWED_BOOKS = "list_unborrowed_books"
LOAN_TOOL_NAMES = (GET_LOAN_STATS, LIST_UNBORROWED_BOOKS)

FIELDS_DESCRIPTION = (
    "분야 필터(KDC 주류). 여러 개면 그중 하나에 속하는 책. null이면 전체. 과학은 자연과학, "
    "공학·의학·요리·육아는 기술과학이다"
)
PERIOD_DESCRIPTION = (
    "기간 프리셋. month와 둘 중 하나만 준다. 날짜는 코드가 계산해 결과의 period로 돌려준다"
)
MONTH_DESCRIPTION = "월 숫자(1~12). '9월'처럼 달로 물을 때. 미래가 아닌 가장 최근의 그 달이다"


def _literal(values: Sequence[str]) -> Any:
    return Literal.__getitem__(tuple(values))


def _filter_fields(axes: Sequence[AnalysisAxis]) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "fields": (
            list[BookField] | None,
            Field(min_length=1, max_length=len(BookField), description=FIELDS_DESCRIPTION),
        )
    }
    for axis in axes:
        fields[axis.name] = (
            _literal(axis.values) | None,
            Field(description=f"{axis.description}. null이면 전체"),
        )
    return fields


def _period_fields() -> dict[str, Any]:
    return {
        "period": (PeriodPreset | None, Field(description=PERIOD_DESCRIPTION)),
        "month": (int | None, Field(ge=1, le=12, description=MONTH_DESCRIPTION)),
    }


def _model(name: str, fields: dict[str, Any]) -> type[ToolInput]:
    return create_model(name, __base__=ToolInput, **fields)


def _book_filter(data: ToolInput, axes: Sequence[AnalysisAxis]) -> BookFilter:
    chosen = {a.name: getattr(data, a.name) for a in axes if getattr(data, a.name) is not None}
    return BookFilter(fields=tuple(data.fields or ()), axes=chosen)


def _collection_tool(axes: Sequence[AnalysisAxis]) -> Tool:
    keys = (FIELD, STATUS, ACQUISITION, *[a.name for a in axes])
    model = _model(
        "CollectionStatusInput",
        {
            "group_by": (
                _literal(keys) | None,
                Field(
                    description="묶을 기준. null이면 합계만. status는 이용 가능·대출 중·분실·훼손"
                ),
            ),
            **_filter_fields(axes),
        },
    )

    async def handler(ctx: ToolContext, data: Any) -> dict[str, Any]:
        result = await analytics.collection_status(
            ctx.session,
            ctx.library_id,
            group_by=data.group_by,
            book_filter=_book_filter(data, axes),
            axes=axes,
        )
        return result.model_dump(mode="json")

    return Tool(
        GET_COLLECTION_STATUS,
        "장서 현황: 사본 수와 서명 수. 제적 사본은 빼고 withdrawn_copies로 따로 센다. 분실·훼손·"
        "대출 중은 센다. 묶으면 그룹마다 센다(값이 0인 그룹 포함).",
        model,
        handler,
        "장서 현황을 세고 있어요",
        record_fields=tuple(model.model_fields),
    )


def _holdings_tool(axes: Sequence[AnalysisAxis]) -> Tool:
    statuses = (HoldingStatus.LOST.value, HoldingStatus.DAMAGED.value, HoldingStatus.ON_LOAN.value)
    model = _model(
        "HoldingsByStatusInput",
        {
            "status": (_literal(statuses), Field(description="분실(lost), 훼손(damaged), 대출 중")),
            **_filter_fields(axes),
            "limit": (int, Field(ge=1, le=LIMIT_MAX, description="보여 줄 사본 수. 보통 20")),
        },
    )

    async def handler(ctx: ToolContext, data: Any) -> dict[str, Any]:
        result = await analytics.holdings_by_status(
            ctx.session,
            ctx.library_id,
            status=HoldingStatus(data.status),
            book_filter=_book_filter(data, axes),
            axes=axes,
            limit=data.limit,
        )
        return result.model_dump(mode="json")

    return Tool(
        LIST_HOLDINGS_BY_STATUS,
        "한 상태의 사본 목록(서명, 저자, 등록번호, 청구기호, 마지막 수정 시각). total은 조건에 "
        "맞는 전체 수이고 truncated면 일부만 보인다.",
        model,
        handler,
        "사본 목록을 찾고 있어요",
        record_fields=tuple(model.model_fields),
    )


def _loan_stats_tool(axes: Sequence[AnalysisAxis]) -> Tool:
    keys = (FIELD, analytics.BOOK, *[a.name for a in axes])
    model = _model(
        "LoanStatsInput",
        {
            **_period_fields(),
            "group_by": (
                _literal(keys) | None,
                Field(
                    description=(
                        "묶을 기준. field면 분야마다 사본 수와 권당 대출도 낸다. book이면 많이 "
                        "빌린 책 순위. null이면 합계만"
                    )
                ),
            ),
            **_filter_fields(axes),
            "top_n": (
                int,
                Field(
                    ge=1, le=TOP_N_MAX, description="책 순위의 권수. 보통 10. 다른 묶기에서는 무시"
                ),
            ),
        },
    )

    async def handler(ctx: ToolContext, data: Any) -> dict[str, Any]:
        result = await analytics.loan_stats(
            ctx.session,
            ctx.library_id,
            period=data.period,
            month=data.month,
            group_by=data.group_by,
            book_filter=_book_filter(data, axes),
            axes=axes,
            top_n=data.top_n,
        )
        return result.model_dump(mode="json")

    return Tool(
        GET_LOAN_STATS,
        "기간 대출 통계: 빌린 날이 기간 안인 대출 수(제적된 사본의 대출 포함). current는 기간과 "
        "상관없이 지금 대출 중·연체 중 건수다. 비교는 기간을 바꿔 두 번 부른다.",
        model,
        handler,
        "대출 기록을 세고 있어요",
        record_fields=tuple(model.model_fields),
    )


def _unborrowed_tool(axes: Sequence[AnalysisAxis]) -> Tool:
    model = _model(
        "UnborrowedBooksInput",
        {
            **_period_fields(),
            **_filter_fields(axes),
            "limit": (int, Field(ge=1, le=LIMIT_MAX, description="보여 줄 서명 수. 보통 20")),
        },
    )

    async def handler(ctx: ToolContext, data: Any) -> dict[str, Any]:
        result = await analytics.unborrowed_books(
            ctx.session,
            ctx.library_id,
            period=data.period,
            month=data.month,
            book_filter=_book_filter(data, axes),
            axes=axes,
            limit=data.limit,
        )
        return result.model_dump(mode="json")

    return Tool(
        LIST_UNBORROWED_BOOKS,
        "기간에 한 번도 빌리지 않은 서명. 기간 시작 전에 등록됐고 지금 소장 사본이 있는 책만. "
        "total은 전체 수이고 truncated면 일부만 보인다.",
        model,
        handler,
        "안 빌린 책을 찾고 있어요",
        record_fields=tuple(model.model_fields),
    )


def analytics_tools(axes: Sequence[AnalysisAxis] = (), *, loans: bool = True) -> tuple[Tool, ...]:
    """운영 에이전트의 분석 tool. 외부 대출 기관은 대출 행이 없어 loans=False로 대출 tool을 뺀다."""
    tools = [_collection_tool(axes), _holdings_tool(axes)]
    if loans:
        tools += [_loan_stats_tool(axes), _unborrowed_tool(axes)]
    return tuple(tools)
