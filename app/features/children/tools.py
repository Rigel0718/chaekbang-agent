"""어린이 기능이 AI 사서에 끼우는 값: 어린이 도서 검색·관련 책 tool, 어린이 검사, 프롬프트 문구.

`app/main.py`가 `children_extension()`을 AI 사서 프로필 조립에 넘긴다. 기능을 빼면 함께 빠진다.
"""

from app.features.children.checks import (
    CHILDREN_RELATED_TOOL_NAME,
    CHILDREN_TOOL_NAME,
    ChildrenCheck,
)
from app.features.children.service import children_book_ids
from app.library.librarian import LibrarianExtension
from app.library.tools import related_tool, search_tool

SEARCH_CHILDREN_BOOKS = search_tool(
    CHILDREN_TOOL_NAME,
    "이 도서관에서 어린이 도서(영유아·초등)로 분류된 소장 도서만 찾는다. 찾는 방식은 "
    "search_collection과 같다. 어린이 요청에만 쓴다.",
    "어린이 도서를 찾고 있어요",
    within=children_book_ids,
)

FIND_RELATED_CHILDREN_BOOKS = related_tool(
    CHILDREN_RELATED_TOOL_NAME,
    "이 도서관에서 어린이 도서로 분류된 소장 도서 중 관련 책만 찾는다. 입력과 방식은 "
    "find_related_books와 같다. 어린이 요청에만 쓴다.",
    "어린이 도서 중 비슷한 책을 찾고 있어요",
    within=children_book_ids,
)

PROMPT_NOTE = """\
어린이 도서
- 어린이 요청은 이용자가 영유아나 초등학생이 읽을 책, 아이와 함께 읽을 책을 찾을 때다. 이때만 \
search_children_books와 find_related_children_books를 쓴다.
- 아이나 나이를 말하지 않은 요청은 공룡처럼 어린이 책이 많은 주제라도 어린이 요청이 아니다. \
search_collection, find_related_books로 찾는다.
- 부모나 어른이 읽을 육아·훈육·교육 책을 찾는 것은 어린이 요청이 아니다.
- 어린이 요청에서 "비슷한 거", "아무거나"는 find_related_children_books로 찾는다. 입력은 \
find_related_books와 같다.
- 어린이 요청에는 두 어린이 tool 결과에 나온 책만 추천한다. 일반 도서를 넣으면 답이 거절된다.
- 맞는 어린이 도서가 없으면 없다고 말하고 희망도서를 안내한다.
"""


def children_extension() -> LibrarianExtension:
    return LibrarianExtension(
        tools=(SEARCH_CHILDREN_BOOKS, FIND_RELATED_CHILDREN_BOOKS),
        final_checks=(ChildrenCheck(),),
        prompt_note=PROMPT_NOTE,
    )
