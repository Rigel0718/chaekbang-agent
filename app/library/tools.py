"""AI 사서의 조회 tool. service를 감싸고, 기관은 실행기가 ToolContext로 주입한다.

도서관 안내(`get_library_guide`)는 입력이 없다. 날짜·요일·반납 예정일은 코드가 계산해 결과에 넣고,
LLM은 날짜를 정하거나 세지 않는다.

쓰기 tool(대출, 반납, 희망도서)은 없다. 기관 개별 기능은 `search_tool`로 검색 범위만 좁힌 tool을
만든다. tool 입력은 실행 기록에 남기지 않는다. 키워드에 이용자 문장의 일부가 들어 있을 수 있어서다.
"""

from collections.abc import Callable
from typing import Any

from pydantic import ConfigDict, Field
from sqlalchemy import Select

from app.agent.tools import Tool, ToolContext, ToolInput
from app.library.recommendation.cards import Shelf, shelf_of
from app.library.recommendation.kdc import kdc_class_name
from app.library.recommendation.lookup import find_books
from app.library.recommendation.search import Candidate, get_candidate, search_collection
from app.library.schemas.guide import DaySchedule, DayStatus, GuideRead, Span
from app.library.services.guide import get_guide

DESCRIPTION_LIMIT = 200
TOC_LIMIT = 600
NO_DESCRIPTION = "소개 정보가 없습니다. 내용을 추측하지 마세요."


class SearchInput(ToolInput):
    keywords: list[str] = Field(
        max_length=5,
        description=(
            "서명, 부제, 저자, 시리즈, 소개에서 찾을 낱말. 비우면 대출 가능한 책을 둘러본다"
        ),
    )


class FindInput(ToolInput):
    query: str = Field(
        max_length=100, description="이용자가 말한 서명이나 저자. 띄어쓰기와 한 글자 오타는 괜찮다"
    )


class GuideInput(ToolInput):
    # 입력이 없다. strict 스키마가 required 목록을 요구해서 빈 목록을 둔다
    model_config = ConfigDict(extra="forbid", json_schema_extra={"required": []})


class DetailInput(ToolInput):
    library_book_id: int = Field(description="검색 결과의 library_book_id")


def _cut(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + "…"


NO_SHELF: Shelf = (None, None)


def _base(candidate: Candidate, shelf: Shelf) -> dict[str, Any]:
    book = candidate.library_book
    synced = candidate.status_synced_at
    location, call_number = shelf
    return {
        "library_book_id": book.id,
        "title": book.shown("title"),
        "subtitle": book.book.subtitle if book.book is not None else None,
        "author": book.shown("author"),
        "publisher": book.shown("publisher"),
        "series_name": book.book.series_name if book.book is not None else None,
        "available_count": candidate.available_count,
        "on_loan_count": candidate.on_loan_count,
        "status_synced_at": synced.isoformat() if synced else None,
        "shelf_location": location,
        "call_number": call_number,
        "call_number_class": kdc_class_name(call_number),
    }


def search_result(candidate: Candidate, shelf: Shelf = NO_SHELF) -> dict[str, Any]:
    return {
        **_base(candidate, shelf),
        "description": _cut(candidate.library_book.shown("description"), DESCRIPTION_LIMIT),
    }


def detail_result(candidate: Candidate, shelf: Shelf = NO_SHELF) -> dict[str, Any]:
    book = candidate.library_book
    description = book.shown("description")
    toc = book.book.table_of_contents if book.book is not None else None
    return {
        **_base(candidate, shelf),
        "recommendable": candidate.recommendable,
        "description": description.strip() if description and description.strip() else None,
        "description_note": None if description and description.strip() else NO_DESCRIPTION,
        "table_of_contents": _cut(toc, TOC_LIMIT),
    }


def search_tool(
    name: str,
    description: str,
    status_label: str,
    within: Callable[[int], Select] | None = None,
) -> Tool:
    """소장 도서 검색 tool. within은 기관 도서 id 조건을 만드는 함수다."""

    async def handler(ctx: ToolContext, data: SearchInput) -> list[dict[str, Any]]:
        found = await search_collection(
            ctx.session,
            ctx.library_id,
            data.keywords,
            within=within(ctx.library_id) if within is not None else None,
        )
        return await _results(ctx, found)

    return Tool(name, description, SearchInput, handler, status_label)


async def _results(ctx: ToolContext, candidates: list[Candidate]) -> list[dict[str, Any]]:
    """검색·찾기 결과. 서가 위치는 카드와 같은 사본에서 뽑는다."""
    shelf = await shelf_of(ctx.session, ctx.library_id, [c.library_book.id for c in candidates])
    return [search_result(c, shelf.get(c.library_book.id, NO_SHELF)) for c in candidates]


async def _find(ctx: ToolContext, data: FindInput) -> list[dict[str, Any]]:
    found = await find_books(ctx.session, ctx.library_id, data.query)
    return await _results(ctx, [f.candidate for f in found])


async def _detail(ctx: ToolContext, data: DetailInput) -> dict[str, Any]:
    candidate = await get_candidate(ctx.session, ctx.library_id, data.library_book_id)
    shelf = await shelf_of(ctx.session, ctx.library_id, [candidate.library_book.id])
    return detail_result(candidate, shelf.get(candidate.library_book.id, NO_SHELF))


SEARCH_COLLECTION = search_tool(
    "search_collection",
    "이 도서관의 소장 도서에서 추천할 수 있는 책을 찾는다. 대출 가능이나 대출 중 사본이 있는 책만 "
    "나오고 최대 10권이다. 소개는 앞부분만 나온다.",
    "소장 도서를 찾고 있어요",
)

FIND_BOOK = Tool(
    "find_book",
    "이 도서관 소장 도서를 서명이나 저자로 찾는다. 이용자가 책 이름이나 작가를 말할 때 쓴다. "
    "검색창과 같은 찾기이고 어린이 구분으로 거르지 않는다. 최대 10권이다.",
    FindInput,
    _find,
    "책을 찾고 있어요",
)

GET_BOOK_DETAIL = Tool(
    "get_book_detail",
    "이 도서관 책 한 권의 소개 전체와 목차, 대출 상태를 본다.",
    DetailInput,
    _detail,
    "책 정보를 확인하고 있어요",
)


GUIDE_NOTE = "여기 없는 내용은 지어내지 말고 대표 연락처 {phone}로 문의하라고 안내한다."
GUIDE_NOTE_NO_PHONE = (
    "여기 없는 내용은 지어내지 말고 도서관 담당자에게 직접 물어보라고 안내한다. "
    "전화번호를 만들지 않는다."
)
GUIDE_NOTE_EMPTY = (
    "이 도서관은 안내 정보를 아직 등록하지 않았다. 운영 시간, 휴관, 위치를 말하지 말고 도서관 "
    "담당자에게 직접 물어보라고 안내한다. 전화번호를 만들지 않는다. 대출 기간은 답해도 된다."
)
STATUS_TEXT = {DayStatus.OPEN: "개관", DayStatus.CLOSED: "휴관", DayStatus.UNKNOWN: "등록 안 됨"}


def _hours(spans: list[Span]) -> list[str]:
    return [f"{s.opens_at:%H:%M}–{s.closes_at:%H:%M}" for s in spans]


def _day(day: DaySchedule) -> dict[str, Any]:
    due = day.due_if_borrowed
    return {
        "date": day.label,
        "status": STATUS_TEXT[day.status],
        "hours": _hours(day.spans),
        "closed_reason": day.closed_reason,
        "due_if_borrowed": due.label if due else None,
        "due_moved_from": due.moved_from_label if due else None,
    }


def guide_note(guide: GuideRead) -> str:
    if not guide.registered:
        return GUIDE_NOTE_EMPTY
    if guide.contact_phone is None:
        return GUIDE_NOTE_NO_PHONE
    return GUIDE_NOTE.format(phone=guide.contact_phone)


def guide_result(guide: GuideRead) -> dict[str, Any]:
    """안내 조회 값을 LLM이 읽기 쉬운 모양으로. 날짜는 사람이 읽는 표기다."""
    hours_known = any(day.spans for day in guide.weekly_hours)
    return {
        "registered": guide.registered,
        "contact_phone": guide.contact_phone,
        "today": {**_day(guide.today), "now": guide.today.now, "open_now": guide.today.open_now},
        "next_days": [_day(d) for d in guide.next_days[1:]],
        "weekly_hours": {
            day.weekday_label: ", ".join(_hours(day.spans))
            if day.spans
            else ("정기 휴관" if hours_known else "등록 안 됨")
            for day in guide.weekly_hours
        },
        "closed_on_public_holidays": guide.closed_on_public_holidays,
        "loan_rules": {
            "loan_days": guide.loan_days,
            "loan_limit": guide.loan_limit,
            "due_on_closed_day": guide.due_on_closed_day.value,
            "due_is_estimate": guide.due_is_estimate,
        },
        "entries": [
            {"kind": e.kind.value, "title": e.title, "body": e.body} for e in guide.entries
        ],
        "note": guide_note(guide),
    }


async def _guide(ctx: ToolContext, data: GuideInput) -> dict[str, Any]:
    return guide_result(await get_guide(ctx.session, ctx.library_id))


GET_LIBRARY_GUIDE = Tool(
    "get_library_guide",
    "이 도서관의 안내: 대표 연락처, 요일별 운영 시간, 오늘과 앞으로 7일의 개관 여부, 그날 빌리면 "
    "반납 예정일, 대출 기간과 권수, 시설 위치와 이용 규칙. 입력은 없다. 날짜는 계산된 값을 그대로 "
    "쓴다.",
    GuideInput,
    _guide,
    "도서관 안내를 확인하고 있어요",
)
