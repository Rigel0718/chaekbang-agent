"""[agent/admin] 분석·초안 tool의 화면용 변환. 분석은 실제 service 결과를 변환에 넣는다."""

from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import Tool, ToolContext
from app.core import clock
from app.features.children.analytics import AUDIENCE_AXIS
from app.library.analytics_tools import (
    GET_COLLECTION_STATUS,
    GET_LOAN_STATS,
    LIST_HOLDINGS_BY_STATUS,
    LIST_UNBORROWED_BOOKS,
    analytics_tools,
)
from app.library.schemas.admin_results import TableResult
from app.library.schemas.analytics import HoldingItem, HoldingList
from tests.library.analytics_helpers import TODAY, book, loan, member

AXES = (AUDIENCE_AXIS,)
EMPTY_FILTERS = {"fields": None, "audience": None}


@pytest.fixture(autouse=True)
def _today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "today", lambda: TODAY)


def _tools() -> dict[str, Tool]:
    return {tool.name: tool for tool in analytics_tools(AXES)}


async def _present(session: AsyncSession, library_id: int, name: str, **inputs: Any):
    tool = _tools()[name]
    data = tool.input_model.model_validate({**EMPTY_FILTERS, **inputs})
    output = await tool.handler(ToolContext(library_id, session), data)
    assert tool.present is not None
    return tool.present(data, output)


async def test_collection_by_field(session: AsyncSession, library_a) -> None:
    """[agent/admin] 장서·대출 묶음 표 / 분야별 장서"""
    await book(session, library_a.id, "available", "available", kdc="813")
    await book(session, library_a.id, kdc=None)
    table = await _present(session, library_a.id, GET_COLLECTION_STATUS, group_by="field")
    assert isinstance(table, TableResult)
    assert table.title == "분야별 장서"
    assert table.columns == ["분야", "권수", "종수"]
    assert table.bar_column == 1
    rows = {row[0]: row[1:] for row in table.rows}
    assert rows["문학"] == [2, 1]
    assert rows["분류 없음"] == [1, 1]
    assert len(table.rows) == 11  # KDC 주류 10 + 분류 없음
    assert (table.caption, table.total, table.truncated) == (None, None, False)


async def test_totals_only_have_no_table(session: AsyncSession, library_a) -> None:
    """[agent/admin] 장서·대출 묶음 표 / 합계만"""
    await book(session, library_a.id, kdc="813")
    assert await _present(session, library_a.id, GET_COLLECTION_STATUS, group_by=None) is None
    loans = await _present(
        session,
        library_a.id,
        GET_LOAN_STATS,
        period="this_month",
        month=None,
        group_by=None,
        top_n=10,
    )
    assert loans is None


async def test_loans_by_field(session: AsyncSession, library_a) -> None:
    """[agent/admin] 장서·대출 묶음 표 / 분야별 대출"""
    _, holdings = await book(session, library_a.id, "available", "available", kdc="400")
    who = await member(session, library_a.id)
    for day in (2, 3, 4):
        await loan(session, holdings[0], who, date(2026, 11, day), date(2026, 11, day))
    table = await _present(
        session,
        library_a.id,
        GET_LOAN_STATS,
        period="this_month",
        month=None,
        group_by="field",
        top_n=10,
    )
    assert table.title == "분야별 대출"
    assert table.columns == ["분야", "대출", "권수", "권당 대출"]
    assert table.bar_column == 1
    assert next(r for r in table.rows if r[0] == "자연과학") == ["자연과학", 3, 2, 1.5]
    assert table.caption == "2026년 11월 1일~19일, 진행 중"


async def test_loans_by_axis_have_no_copy_columns(session: AsyncSession, library_a) -> None:
    """[agent/admin] 장서·대출 묶음 표 / 분야별 대출 (분야가 아닌 묶기는 대출 열만)"""
    await book(session, library_a.id, kdc="400")
    table = await _present(
        session,
        library_a.id,
        GET_LOAN_STATS,
        period="last_month",
        month=None,
        group_by="audience",
        top_n=10,
    )
    assert table.title == "구분별 대출"
    assert table.columns == ["구분", "대출"]
    assert all(len(row) == 2 for row in table.rows)
    assert table.caption == "2026년 10월 1일~31일"


async def test_top_books(session: AsyncSession, library_a) -> None:
    """[agent/admin] 장서·대출 묶음 표 / 많이 빌린 책"""
    who = await member(session, library_a.id)
    for n in range(3):
        _, holdings = await book(session, library_a.id, title=f"순위 책 {n}")
        for _ in range(n + 1):
            await loan(session, holdings[0], who, date(2026, 11, 3), date(2026, 11, 4))
    table = await _present(
        session,
        library_a.id,
        GET_LOAN_STATS,
        period="this_month",
        month=None,
        group_by="book",
        top_n=2,
    )
    assert table.title == "많이 빌린 책"
    assert table.columns == ["순위", "도서명", "저자", "대출"]
    assert table.bar_column is None
    assert [row[0] for row in table.rows] == [1, 2]
    assert [row[1] for row in table.rows] == ["순위 책 2", "순위 책 1"]
    assert (table.total, table.truncated) == (3, True)


async def test_filter_caption(session: AsyncSession, library_a) -> None:
    """[agent/admin] 장서·대출 묶음 표 / 분야로 거른 결과"""
    await book(session, library_a.id, kdc="400")
    table = await _present(
        session,
        library_a.id,
        GET_COLLECTION_STATUS,
        group_by="acquisition_type",
        fields=["자연과학"],
        audience="children",
    )
    assert table.title == "입수 구분별 장서"
    assert table.caption == "자연과학, 어린이 기준"


async def test_lost_holdings(session: AsyncSession, library_a) -> None:
    """[agent/admin] 사본·서명 목록 표 / 분실 사본"""
    await book(session, library_a.id, "lost", title="잃은 책", call_number="813-가")
    table = await _present(session, library_a.id, LIST_HOLDINGS_BY_STATUS, status="lost", limit=20)
    assert table.title == "분실 사본"
    assert table.columns == ["도서명", "저자", "등록번호", "청구기호"]
    assert table.bar_column is None
    [row] = table.rows
    assert row[0] == "잃은 책" and row[2].startswith("AN") and row[3] == "813-가"
    assert table.caption is None


async def test_truncated_unborrowed(session: AsyncSession, library_a) -> None:
    """[agent/admin] 사본·서명 목록 표 / 잘린 목록"""
    for n in range(3):
        await book(session, library_a.id, title=f"안 빌린 {n}")
    table = await _present(
        session,
        library_a.id,
        LIST_UNBORROWED_BOOKS,
        period="this_year",
        month=None,
        limit=2,
    )
    assert table.title == "안 빌린 책"
    assert table.columns == ["도서명", "저자", "권수"]
    assert len(table.rows) == 2
    assert (table.total, table.truncated) == (3, True)
    assert table.caption == "2026년 1월 1일~11월 19일, 진행 중"


def test_external_on_loan_caption() -> None:
    """[agent/admin] 사본·서명 목록 표 / 외부 대출 기관의 대출 중 사본"""
    tool = _tools()[LIST_HOLDINGS_BY_STATUS]
    data = tool.input_model.model_validate({**EMPTY_FILTERS, "status": "on_loan", "limit": 20})

    def item(n: int, synced: datetime) -> HoldingItem:
        return HoldingItem(
            library_book_id=n,
            title=f"책 {n}",
            author="저자",
            accession_number=f"E{n}",
            call_number=None,
            status="on_loan",
            updated_at=synced,
            last_synced_at=synced,
        )

    # 11월 19일 16시 UTC는 기관 시간대(서울)로 11월 20일이다
    late = datetime(2026, 11, 19, 16, 0, tzinfo=UTC)
    output = HoldingList(
        status="on_loan",
        total=2,
        shown=2,
        truncated=False,
        items=[item(1, datetime(2026, 11, 2, tzinfo=UTC)), item(2, late)],
    ).model_dump(mode="json")
    table = tool.present(data, output)
    assert table.title == "대출 중 사본"
    assert table.caption == "11월 20일 가져온 파일 기준"
