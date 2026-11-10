"""AI 사서 테스트 도우미: 가짜 LLM 응답, 프로필 실행, 소장 도서 준비."""

from itertools import count
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import LlmTurn, Stop, ToolCall, Usage
from app.agent.profile import Profile
from app.agent.runner import RunEvent, run
from app.library.librarian import LibrarianExtension, build_librarian_profiles
from app.library.models.library import LoanMode
from tests.agent.fakes import FakeLlm
from tests.helpers import add_book, add_holding, add_library_book, make_isbn

_numbers = count(1)


def call(name: str, arguments: Any, id: str | None = None) -> ToolCall:
    return ToolCall(id or f"c{next(_numbers)}", name, arguments)


def turn(*calls: ToolCall) -> LlmTurn:
    return LlmTurn(Stop.TOOL_USE, calls, usage=Usage(input_tokens=10, output_tokens=5))


def search(*keywords: str, name: str = "search_collection") -> LlmTurn:
    return turn(call(name, {"keywords": list(keywords)}))


def detail(library_book_id: int) -> LlmTurn:
    return turn(call("get_book_detail", {"library_book_id": library_book_id}))


def submit(
    message: str = "추천해요.", *book_ids: int, suggest: bool = False, reason: str = "좋아요"
) -> LlmTurn:
    return turn(
        call(
            "submit_answer",
            {
                "message": message,
                "recommendations": [{"library_book_id": i, "reason": reason} for i in book_ids],
                "suggest_book_request": suggest,
            },
        )
    )


def librarian(loan_mode: LoanMode = LoanMode.INTERNAL, *extensions: LibrarianExtension) -> Profile:
    return build_librarian_profiles(extensions)[loan_mode]


async def run_librarian(
    session: AsyncSession,
    llm: FakeLlm,
    library_id: int,
    user_text: str = "공룡 책 추천해줘",
    *,
    prof: Profile | None = None,
    **values: Any,
) -> list[RunEvent]:
    return [
        event
        async for event in run(
            session=session,
            llm=llm,
            profile=prof or librarian(),
            library_id=library_id,
            user_text=user_text,
            **values,
        )
    ]


async def add_held_book(
    session: AsyncSession,
    library_id: int,
    *statuses: str,
    isbn: str | None = None,
    official: dict | None = None,
    holding: dict | None = None,
    **values: Any,
) -> Any:
    """기관 도서와 상태별 사본을 만든다. official을 주면 공식 서지를 만들어 연결한다."""
    book_id = None
    if official is not None:
        isbn = isbn or make_isbn(next(_numbers) % 900 + 50)
        book = await add_book(session, isbn, **{"title": values.get("title", "공식"), **official})
        book_id = book["id"]
    values.setdefault("title", "테스트 도서")
    library_book = await add_library_book(session, library_id, isbn, book_id=book_id, **values)
    for status in statuses or ("available",):
        await add_holding(
            session,
            library_id,
            library_book["id"],
            f"LB{next(_numbers):06d}",
            status=status,
            **(holding or {}),
        )
    return library_book
