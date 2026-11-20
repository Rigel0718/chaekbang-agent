"""[agent/admin], [library/collection-analytics] 운영 에이전트 tool·프로필과 결과 허용 목록."""

from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import ToolContext
from app.core import clock
from app.features.children.analytics import AUDIENCE_AXIS, admin_extension
from app.library.admin_agent import ANSWER_TOOL, AdminAnswer, build_admin_profiles
from app.library.analytics_tools import (
    GET_COLLECTION_STATUS,
    GET_LOAN_STATS,
    LIST_HOLDINGS_BY_STATUS,
    LIST_UNBORROWED_BOOKS,
    analytics_tools,
)
from app.library.models.library import LoanMode
from app.library.schemas.analytics import CollectionStatus, HoldingList, LoanStats, UnborrowedBooks
from tests.library.analytics_helpers import TODAY, book, loan, member

ANALYSIS_TOOLS = {
    GET_COLLECTION_STATUS,
    LIST_HOLDINGS_BY_STATUS,
    GET_LOAN_STATS,
    LIST_UNBORROWED_BOOKS,
}

# 결과 필드 허용 목록. 필드를 더하면 이 목록을 함께 고쳐야 한다(개인정보가 아닌지 본 뒤에).
ALLOWED_RESULT_FIELDS = {
    GET_COLLECTION_STATUS: {
        "group_by",
        "copies",
        "titles",
        "withdrawn_copies",
        "groups[].key",
        "groups[].label",
        "groups[].copies",
        "groups[].titles",
    },
    LIST_HOLDINGS_BY_STATUS: {
        "status",
        "total",
        "shown",
        "truncated",
        "items[].library_book_id",
        "items[].title",
        "items[].author",
        "items[].accession_number",
        "items[].call_number",
        "items[].status",
        "items[].updated_at",
        "items[].last_synced_at",
    },
    GET_LOAN_STATS: {
        "period.start",
        "period.end",
        "period.label",
        "period.in_progress",
        "group_by",
        "loans",
        "groups[].key",
        "groups[].label",
        "groups[].loans",
        "groups[].copies",
        "groups[].loans_per_copy",
        "ranking.total",
        "ranking.shown",
        "ranking.truncated",
        "ranking.items[].library_book_id",
        "ranking.items[].title",
        "ranking.items[].author",
        "ranking.items[].loans",
        "ranking.items[].in_collection",
        "current.on_loan",
        "current.overdue",
    },
    LIST_UNBORROWED_BOOKS: {
        "period.start",
        "period.end",
        "period.label",
        "period.in_progress",
        "total",
        "shown",
        "truncated",
        "items[].library_book_id",
        "items[].title",
        "items[].author",
        "items[].copies",
    },
}
RESULT_MODELS = {
    GET_COLLECTION_STATUS: CollectionStatus,
    LIST_HOLDINGS_BY_STATUS: HoldingList,
    GET_LOAN_STATS: LoanStats,
    LIST_UNBORROWED_BOOKS: UnborrowedBooks,
}


def _paths(schema: dict[str, Any], defs: dict[str, Any], prefix: str = "") -> set[str]:
    """JSON Schema의 객체 필드 경로. 목록은 `[]`, 중첩 객체는 `.`로 잇는다."""
    if "$ref" in schema:
        return _paths(defs[schema["$ref"].split("/")[-1]], defs, prefix)
    for option in schema.get("anyOf", []):
        if option.get("type") != "null":
            return _paths(option, defs, prefix)
    if schema.get("type") == "array":
        return _paths(schema["items"], defs, prefix + "[]")
    if schema.get("type") == "object" and "properties" in schema:
        paths: set[str] = set()
        for name, sub in schema["properties"].items():
            path = f"{prefix}.{name}" if prefix else name
            nested = _paths(sub, defs, path)
            paths |= nested or {path}
        return paths
    return set()


def _strict_ok(schema: dict[str, Any]) -> None:
    """strict 스키마 조건: 객체마다 추가 필드 금지, 모든 필드가 필수."""
    nodes = [schema, *schema.get("$defs", {}).values()]
    while nodes:
        node = nodes.pop()
        if not isinstance(node, dict):
            continue
        if node.get("type") == "object":
            assert node.get("additionalProperties") is False
            assert set(node.get("required", [])) == set(node.get("properties", {}))
        for value in node.values():
            if isinstance(value, dict):
                nodes.append(value)
            elif isinstance(value, list):
                nodes.extend(v for v in value if isinstance(v, dict))


def _tools(axes=(AUDIENCE_AXIS,)) -> dict[str, Any]:
    return {t.name: t for t in analytics_tools(axes)}


def test_result_fields_allowlist() -> None:
    """[library/collection-analytics] 분석 결과의 개인정보 / 결과 필드 목록"""
    for name, model in RESULT_MODELS.items():
        schema = model.model_json_schema()
        assert _paths(schema, schema.get("$defs", {})) == ALLOWED_RESULT_FIELDS[name], name


def test_tool_schemas_are_strict() -> None:
    """[library/collection-analytics] 분석 축 / 축 없는 조립 (축 있음·없음 모두 strict 스키마)"""
    for axes in ((), (AUDIENCE_AXIS,)):
        for tool in analytics_tools(axes):
            _strict_ok(tool.spec.parameters)


def test_no_axis_assembly() -> None:
    """[library/collection-analytics] 분석 축 / 축 없는 조립"""
    for tool in analytics_tools(()):
        assert "audience" not in str(tool.spec.parameters), tool.name
    with_axis = _tools()[GET_COLLECTION_STATUS].spec.parameters
    assert "audience" in with_axis["properties"]


def test_input_rejects_library_id() -> None:
    """[library/collection-analytics] 분석의 기관 범위 / 입력의 기관 값"""
    model = _tools()[GET_COLLECTION_STATUS].input_model
    with pytest.raises(ValidationError):
        model.model_validate({"group_by": None, "fields": None, "audience": None, "library_id": 2})


def test_input_rejects_unknown_field_and_withdrawn() -> None:
    """[library/collection-analytics] 공통 필터 / 없는 분야 값"""
    tools = _tools()
    with pytest.raises(ValidationError):
        tools[GET_COLLECTION_STATUS].input_model.model_validate(
            {"group_by": None, "fields": ["과학"], "audience": None}
        )
    with pytest.raises(ValidationError):
        tools[LIST_HOLDINGS_BY_STATUS].input_model.model_validate(
            {"status": "withdrawn", "fields": None, "audience": None, "limit": 20}
        )
    with pytest.raises(ValidationError):
        tools[GET_LOAN_STATS].input_model.model_validate(
            {
                "period": "this_month",
                "month": None,
                "group_by": "book",
                "fields": None,
                "audience": None,
                "top_n": 21,
            }
        )


def test_inputs_are_all_recorded() -> None:
    """[library/collection-analytics] 분석 결과의 개인정보 / 입력 기록"""
    stats = _tools()[GET_LOAN_STATS]
    assert set(stats.record_fields) == {
        "period",
        "month",
        "group_by",
        "fields",
        "audience",
        "top_n",
    }
    for tool in analytics_tools((AUDIENCE_AXIS,)):
        assert set(tool.record_fields) == set(tool.input_model.model_fields), tool.name


async def test_tool_handler_runs_service(
    session: AsyncSession, library_a, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[library/collection-analytics] 분야별 권당 대출 / 권당 대출 (tool로 부름)"""
    monkeypatch.setattr(clock, "today", lambda: TODAY)
    _, holdings = await book(session, library_a.id, "available", "available", kdc="400")
    who = await member(session, library_a.id)
    for day in (2, 3, 4):
        await loan(session, holdings[0], who, date(2026, 11, day), date(2026, 11, day))
    tool = _tools()[GET_LOAN_STATS]
    data = tool.input_model.model_validate(
        {
            "period": "this_month",
            "month": None,
            "group_by": "field",
            "fields": ["자연과학"],
            "audience": None,
            "top_n": 10,
        }
    )
    result = await tool.handler(ToolContext(library_a.id, session), data)
    science = next(g for g in result["groups"] if g["key"] == "자연과학")
    assert (science["loans"], science["copies"], science["loans_per_copy"]) == (3, 2, 1.5)
    assert result["period"]["label"] == "2026년 11월 1일~19일"


# 운영 에이전트 프로필


def test_profile_tools_by_loan_mode() -> None:
    """[agent/admin] 운영 방식별 tool / 자체 대출 기관"""
    profiles = build_admin_profiles([admin_extension()])
    internal = {t.name for t in profiles[LoanMode.INTERNAL].tools}
    assert internal == ANALYSIS_TOOLS | {
        "search_collection",
        "draft_curation",
        "list_overdue_loans",
        "draft_overdue_notice",
    }
    assert profiles[LoanMode.INTERNAL].answer_tool is ANSWER_TOOL


def test_profile_external_has_no_loan_tools() -> None:
    """[agent/admin] 운영 방식별 tool / 외부 대출 기관"""
    external = {t.name for t in build_admin_profiles([admin_extension()])[LoanMode.EXTERNAL].tools}
    assert external == {
        GET_COLLECTION_STATUS,
        LIST_HOLDINGS_BY_STATUS,
        "search_collection",
        "draft_curation",
    }


def test_profile_has_no_approval_tools() -> None:
    """[agent/admin] 운영 방식별 tool / 승인 tool 없음"""
    for profile in build_admin_profiles([admin_extension()]).values():
        names = {t.name for t in profile.tools}
        words = ("approve", "reject", "publish", "confirm")
        assert not {n for n in names if any(w in n for w in words)}
        writes = names - ANALYSIS_TOOLS - {"search_collection", "list_overdue_loans"}
        assert writes <= {"draft_curation", "draft_overdue_notice"}


def test_answer_length_limit() -> None:
    """[agent/admin] 운영 에이전트 최종 답 / 길이 초과"""
    with pytest.raises(ValidationError):
        AdminAnswer.model_validate({"message": "가" * 601, "unsupported": None})
    with pytest.raises(ValidationError):
        AdminAnswer.model_validate({"message": "답", "unsupported": "unknown"})
    assert ANSWER_TOOL.record_fields == ("unsupported",)


def test_prompt_without_children_feature() -> None:
    """[features/children] 운영 에이전트 어린이 문구 / 기능 없는 프롬프트"""
    plain = build_admin_profiles()
    with_children = build_admin_profiles([admin_extension()])
    for mode in LoanMode:
        assert "audience" not in plain[mode].system_prompt
        assert "audience=children" in with_children[mode].system_prompt
        for tool in plain[mode].tools:
            assert "audience" not in str(tool.spec.parameters)


def test_external_prompt_has_no_overdue_notice_rules() -> None:
    """[agent/admin] 운영 방식별 tool / 외부 대출 기관 (연체 안내 규칙은 자체 대출 기관 문구에만)"""
    profiles = build_admin_profiles([admin_extension()])
    external = profiles[LoanMode.EXTERNAL].system_prompt
    internal = profiles[LoanMode.INTERNAL].system_prompt
    for word in ("draft_overdue_notice", "list_overdue_loans", "{이름}"):
        assert word not in external, word
        assert word in internal, word
    assert (
        "unsupported=no_data로 답하고, 관리 화면·승인·연체 안내 목록을 안내하지 않는다" in external
    )
