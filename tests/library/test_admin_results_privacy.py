"""[agent/admin] 결과 사건의 개인정보와 기관 범위: 열 허용 목록, 심은 회원 값, 다른 기관 값.

표(`TableResult`)의 칸은 일반 값이라 필드 이름만으로는 막을 수 없다. 변환이 낼 수 있는 열 이름을
tool마다 고정하고, 심은 회원 값이 결과에 없는지 실제로 돌려 본다. 열을 더하면 이 목록을 고친다
(개인정보가 아닌지 본 뒤에).
"""

import itertools
import json
from datetime import date
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import Tool, ToolContext
from app.core import clock
from app.features.children.analytics import AUDIENCE_AXIS
from app.library.analytics.fields import Field
from app.library.analytics_tools import (
    GET_COLLECTION_STATUS,
    GET_LOAN_STATS,
    LIST_HOLDINGS_BY_STATUS,
    LIST_UNBORROWED_BOOKS,
    analytics_tools,
)
from app.library.curation_tools import DRAFT_CURATION
from app.library.overdue_tools import DRAFT_OVERDUE_NOTICE
from app.library.purchase_tools import DRAFT_PURCHASE_REQUEST
from tests.conftest import Tenant
from tests.helpers import VALID_ISBN, add_held_book, add_member
from tests.library.analytics_helpers import TODAY, book, loan
from tests.purchase_helpers import add_book_request

AXES = (AUDIENCE_AXIS,)
GROUP_NAMES = {"분야", "상태", "입수 구분", "구분"}

# tool마다 결과 표에 나올 수 있는 열. 회원·기증자 열은 넣지 않는다.
ALLOWED_COLUMNS = {
    GET_COLLECTION_STATUS: GROUP_NAMES | {"권수", "종수"},
    GET_LOAN_STATS: GROUP_NAMES | {"대출", "권수", "권당 대출", "순위", "도서명", "저자"},
    LIST_HOLDINGS_BY_STATUS: {"도서명", "저자", "등록번호", "청구기호"},
    LIST_UNBORROWED_BOOKS: {"도서명", "저자", "권수"},
}

CANARY_NAME = "카나리아회원"
CANARY_NUMBER = "CANARY7788"
CANARY_PHONE = "01077778888"
CANARY_DONOR = "카나리아기증자"
CANARIES = (CANARY_NAME, CANARY_NUMBER, CANARY_PHONE, CANARY_DONOR)


@pytest.fixture(autouse=True)
def _today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "today", lambda: TODAY)


def _inputs(name: str) -> list[dict[str, Any]]:
    """그 tool의 입력을 여러 갈래로. 필터는 없음·분야 둘·어린이."""
    filters = [
        {"fields": None, "audience": None},
        {"fields": [Field.NATURAL_SCIENCES, Field.UNCLASSIFIED], "audience": None},
        {"fields": None, "audience": "children"},
    ]
    if name == GET_COLLECTION_STATUS:
        rest = [{"group_by": g} for g in (None, "field", "status", "acquisition_type", "audience")]
    elif name == GET_LOAN_STATS:
        rest = [
            {"period": "last_365_days", "month": None, "group_by": g, "top_n": 20}
            for g in (None, "field", "book", "audience")
        ]
    elif name == LIST_HOLDINGS_BY_STATUS:
        rest = [{"status": s, "limit": 50} for s in ("lost", "damaged", "on_loan")]
    else:
        rest = [{"period": "this_year", "month": None, "limit": 50}]
    return [{**f, **r} for f, r in itertools.product(filters, rest)]


async def _analytics_results(session: AsyncSession, library_id: int) -> dict[str, list[Any]]:
    out: dict[str, list[Any]] = {}
    for tool in analytics_tools(AXES):
        out[tool.name] = []
        for values in _inputs(tool.name):
            data = tool.input_model.model_validate(values)
            output = await tool.handler(ToolContext(library_id, session), data)
            value = tool.present(data, output)
            if value is not None:
                out[tool.name].append(value)
    return out


async def _draft(session: AsyncSession, library_id: int, tool: Tool, values: dict) -> Any:
    data = tool.input_model.model_validate(values)
    output = await tool.handler(ToolContext(library_id, session), data)
    return tool.present(data, output)


async def _plant(session: AsyncSession, library_id: int) -> None:
    """회원 값과 기증처가 있는 대출·연체·희망도서."""
    who = await add_member(session, library_id, CANARY_NUMBER, CANARY_NAME, phone=CANARY_PHONE)
    _, holdings = await book(
        session,
        library_id,
        "available",
        "lost",
        "damaged",
        kdc="400",
        acquisition="donated",
        donor=CANARY_DONOR,
    )
    _, late = await book(session, library_id, "available", kdc="813")
    await loan(session, holdings[0], who, date(2026, 3, 1), returned_on=date(2026, 3, 9))
    await loan(session, late[0], who, date(2026, 11, 1), due_on=date(2026, 11, 10))  # 연체
    await add_book_request(session, library_id, member_id=who.id, isbn=VALID_ISBN)


async def test_columns_allowlist(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/admin] 결과 사건의 개인정보와 기관 범위 / 정한 열만"""
    await _plant(session, library_a.id)
    results = await _analytics_results(session, library_a.id)
    assert set(results) == set(ALLOWED_COLUMNS)
    for name, tables in results.items():
        assert tables, name
        for table in tables:
            assert set(table.columns) <= ALLOWED_COLUMNS[name], (name, table.columns)


async def test_planted_member_values_absent(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/admin] 결과 사건의 개인정보와 기관 범위 / 회원 값 없음"""
    await _plant(session, library_a.id)
    values = [
        v for tables in (await _analytics_results(session, library_a.id)).values() for v in tables
    ]
    ids = [(await add_held_book(session, library_a.id, title=f"공룡 {i}"))["id"] for i in range(3)]
    values.append(
        await _draft(
            session,
            library_a.id,
            DRAFT_CURATION,
            {"title": "공룡", "intro": None, "library_book_ids": ids, "reasons": ["공룡"] * 3},
        )
    )
    values.append(
        await _draft(
            session,
            library_a.id,
            DRAFT_OVERDUE_NOTICE,
            {"template": "{이름}님, '{서명}' 반납 예정일 {반납예정일}이 지났어요"},
        )
    )
    values.append(
        await _draft(
            session,
            library_a.id,
            DRAFT_PURCHASE_REQUEST,
            {
                "title": "보충",
                "note": None,
                "period": None,
                "items": [{"isbn": VALID_ISBN, "quantity": 1, "reason": None}],
            },
        )
    )
    assert [v.kind for v in values[-3:]] == ["draft", "draft", "draft"]
    dumped = json.dumps([v.model_dump(mode="json") for v in values], ensure_ascii=False)
    for canary in CANARIES:
        assert canary not in dumped


async def test_other_library_values_absent(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[agent/admin] 결과 사건의 개인정보와 기관 범위 / 다른 기관 값 없음"""
    await book(session, library_a.id, "available", "lost", title="우리 책", kdc="400")
    _, theirs = await book(
        session, library_b.id, "available", "lost", "on_loan", title="다른 기관 책", kdc="400"
    )
    results = await _analytics_results(session, library_a.id)
    dumped = json.dumps(
        [t.model_dump(mode="json") for tables in results.values() for t in tables],
        ensure_ascii=False,
    )
    assert "우리 책" in dumped
    assert "다른 기관 책" not in dumped
    for holding in theirs:
        assert holding["accession_number"] not in dumped
