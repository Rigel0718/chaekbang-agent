"""AI 사서의 조회 tool. service를 감싸고, 기관은 실행기가 ToolContext로 주입한다.

쓰기 tool(대출, 반납, 희망도서)은 없다. 기관 개별 기능은 `search_tool`로 검색 범위만 좁힌 tool을
만든다. tool 입력은 실행 기록에 남기지 않는다. 키워드에 이용자 문장의 일부가 들어 있을 수 있어서다.
"""

from collections.abc import Callable
from typing import Any

from pydantic import Field
from sqlalchemy import Select

from app.agent.tools import Tool, ToolContext, ToolInput
from app.library.recommendation.search import Candidate, get_candidate, search_collection

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


class DetailInput(ToolInput):
    library_book_id: int = Field(description="검색 결과의 library_book_id")


def _cut(text: str | None, limit: int) -> str | None:
    if text is None:
        return None
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + "…"


def _base(candidate: Candidate) -> dict[str, Any]:
    book = candidate.library_book
    synced = candidate.status_synced_at
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
    }


def search_result(candidate: Candidate) -> dict[str, Any]:
    return {
        **_base(candidate),
        "description": _cut(candidate.library_book.shown("description"), DESCRIPTION_LIMIT),
    }


def detail_result(candidate: Candidate) -> dict[str, Any]:
    book = candidate.library_book
    description = book.shown("description")
    toc = book.book.table_of_contents if book.book is not None else None
    return {
        **_base(candidate),
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
        return [search_result(c) for c in found]

    return Tool(name, description, SearchInput, handler, status_label)


async def _detail(ctx: ToolContext, data: DetailInput) -> dict[str, Any]:
    return detail_result(await get_candidate(ctx.session, ctx.library_id, data.library_book_id))


SEARCH_COLLECTION = search_tool(
    "search_collection",
    "이 도서관의 소장 도서에서 추천할 수 있는 책을 찾는다. 대출 가능이나 대출 중 사본이 있는 책만 "
    "나오고 최대 10권이다. 소개는 앞부분만 나온다.",
    "소장 도서를 찾고 있어요",
)

GET_BOOK_DETAIL = Tool(
    "get_book_detail",
    "이 도서관 책 한 권의 소개 전체와 목차, 대출 상태를 본다.",
    DetailInput,
    _detail,
    "책 정보를 확인하고 있어요",
)
