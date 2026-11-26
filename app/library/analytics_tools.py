"""운영 에이전트의 분석 tool 네 개. service(`services/analytics.py`)를 감싸고 기관은 실행기가
주입한다.

입력 모델은 조립 때 만든다. 등록된 분석 축의 이름이 묶기 값과 필터 필드가 되고, 축이 없으면 그
필드 자체가 없다. LLM이 정하는 값은 enum과 상한 있는 정수뿐이다. 날짜는 코드가 계산한다.

입력은 모두 실행 기록에 남긴다(enum과 정수라 이용자 문장이 섞이지 않는다). 평가는 이 기록으로
tool 선택을 판정한다. 결과는 service 스키마를 그대로 JSON으로 낸다.

화면용 변환(`present_*`)은 그 입력과 결과(지금 분석 결과 모델)만 읽어 표(`TableResult`)를 만든다.
DB를 읽지 않는다. 묶지 않은 장서·대출은 표를 내지 않는다(답 문장에 있다). 열 이름은 허용 목록
테스트(`tests/library/test_admin_results_privacy.py`)가 고정한다.
"""

from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import Field, create_model

from app.agent.tools import Tool, ToolContext, ToolInput
from app.core.config import get_settings
from app.library.analytics.axes import AnalysisAxis
from app.library.analytics.fields import Field as BookField
from app.library.analytics.periods import Period, PeriodPreset
from app.library.analytics.scope import ACQUISITION, FIELD, STATUS, STATUS_LABELS, BookFilter
from app.library.models.catalog import HoldingStatus
from app.library.schemas.admin_results import TableResult
from app.library.schemas.analytics import (
    LIMIT_MAX,
    TOP_N_MAX,
    CollectionStatus,
    HoldingList,
    LoanStats,
    UnborrowedBooks,
)
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


# --- 화면용 변환 ---

GROUP_HEADERS = {FIELD: "분야", STATUS: "상태", ACQUISITION: "입수 구분"}
OTHER_GROUP = "구분"  # 기관 개별 기능의 축. 이름을 부르지 않는다
# 열 이름은 화면 말이다: 권수(사본 수), 종수(서명 수), 도서명(서명)
COLLECTION_COLUMNS = ("권수", "종수")
LOAN_COLUMNS = ("대출",)
LOAN_FIELD_COLUMNS = ("대출", "권수", "권당 대출")
RANKING_COLUMNS = ("순위", "도서명", "저자", "대출")
HOLDING_COLUMNS = ("도서명", "저자", "등록번호", "청구기호")
UNBORROWED_COLUMNS = ("도서명", "저자", "권수")


def _group_header(group_by: str) -> str:
    return GROUP_HEADERS.get(group_by, OTHER_GROUP)


def _period_text(period: Period) -> str:
    return f"{period.label}, 진행 중" if period.in_progress else period.label


def _filter_text(data: Any, axes: Sequence[AnalysisAxis]) -> str | None:
    names = [str(f) for f in (data.fields or ())]
    for axis in axes:
        value = getattr(data, axis.name)
        if value is not None:
            names.append(axis.labels[value])
    return f"{', '.join(names)} 기준" if names else None


def _synced_text(times: Sequence[datetime | None]) -> str | None:
    known = [t for t in times if t is not None]
    if not known:
        return None
    day = max(known).astimezone(ZoneInfo(get_settings().library_timezone))
    return f"{day.month}월 {day.day}일 가져온 파일 기준"


def _caption(*parts: str | None) -> str | None:
    shown = [p for p in parts if p]
    return " · ".join(shown) if shown else None


def present_collection(axes: Sequence[AnalysisAxis]):
    def present(data: Any, output: dict[str, Any]) -> TableResult | None:
        result = CollectionStatus.model_validate(output)
        if result.group_by is None:
            return None
        header = _group_header(result.group_by)
        return TableResult(
            title=f"{header}별 장서",
            caption=_caption(_filter_text(data, axes)),
            columns=[header, *COLLECTION_COLUMNS],
            rows=[[g.label, g.copies, g.titles] for g in result.groups],
            bar_column=1,
            total=None,
            truncated=False,
        )

    return present


def present_loans(axes: Sequence[AnalysisAxis]):
    def present(data: Any, output: dict[str, Any]) -> TableResult | None:
        result = LoanStats.model_validate(output)
        caption = _caption(_period_text(result.period), _filter_text(data, axes))
        if result.group_by is None:
            return None
        if result.ranking is not None:
            ranking = result.ranking
            return TableResult(
                title="많이 빌린 책",
                caption=caption,
                columns=list(RANKING_COLUMNS),
                rows=[[i, b.title, b.author, b.loans] for i, b in enumerate(ranking.items, 1)],
                bar_column=None,
                total=ranking.total if ranking.truncated else None,
                truncated=ranking.truncated,
            )
        header = _group_header(result.group_by)
        by_field = result.group_by == FIELD
        return TableResult(
            title=f"{header}별 대출",
            caption=caption,
            columns=[header, *(LOAN_FIELD_COLUMNS if by_field else LOAN_COLUMNS)],
            rows=[
                [g.label, g.loans, g.copies, g.loans_per_copy] if by_field else [g.label, g.loans]
                for g in result.groups
            ],
            bar_column=1,
            total=None,
            truncated=False,
        )

    return present


def present_holdings(axes: Sequence[AnalysisAxis]):
    def present(data: Any, output: dict[str, Any]) -> TableResult:
        result = HoldingList.model_validate(output)
        synced = _synced_text([item.last_synced_at for item in result.items])
        return TableResult(
            title=f"{STATUS_LABELS[result.status]} 사본",
            caption=_caption(_filter_text(data, axes), synced),
            columns=list(HOLDING_COLUMNS),
            rows=[
                [item.title, item.author, item.accession_number, item.call_number]
                for item in result.items
            ],
            bar_column=None,
            total=result.total if result.truncated else None,
            truncated=result.truncated,
        )

    return present


def present_unborrowed(axes: Sequence[AnalysisAxis]):
    def present(data: Any, output: dict[str, Any]) -> TableResult:
        result = UnborrowedBooks.model_validate(output)
        return TableResult(
            title="안 빌린 책",
            caption=_caption(_period_text(result.period), _filter_text(data, axes)),
            columns=list(UNBORROWED_COLUMNS),
            rows=[[item.title, item.author, item.copies] for item in result.items],
            bar_column=None,
            total=result.total if result.truncated else None,
            truncated=result.truncated,
        )

    return present


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
        present=present_collection(axes),
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
        present=present_holdings(axes),
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
        present=present_loans(axes),
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
        present=present_unborrowed(axes),
    )


def analytics_tools(axes: Sequence[AnalysisAxis] = (), *, loans: bool = True) -> tuple[Tool, ...]:
    """운영 에이전트의 분석 tool. 외부 대출 기관은 대출 행이 없어 loans=False로 대출 tool을 뺀다."""
    tools = [_collection_tool(axes), _holdings_tool(axes)]
    if loans:
        tools += [_loan_stats_tool(axes), _unborrowed_tool(axes)]
    return tuple(tools)
