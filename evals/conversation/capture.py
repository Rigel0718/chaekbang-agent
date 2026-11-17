"""tool 입력과 결과를 평가 안에서만 받는다.

제품은 검색 낱말을 실행 기록에 남기지 않는다(`record_fields` 없음). 평가는 프로필의 책 tool
handler를 감싸 입력과 결과의 책 id를 메모리에 적고, 평가 결과 파일(저장소 밖)에만 쓴다. 제품의
tool 정의, 실행 기록, 노출 기록은 바꾸지 않는다. 평가 문장은 사람이 쓴 세트 문장이라 개인정보가
없다.
"""

from dataclasses import dataclass, field, replace
from typing import Any

from app.agent.profile import Profile
from app.agent.tools import Tool, ToolContext
from app.library.tools import NO_KEYWORD_MATCH
from evals.librarian.checks import RELATED_TOOLS, SEARCH_TOOLS

CAPTURED_TOOLS = (*SEARCH_TOOLS, *RELATED_TOOLS)


@dataclass
class ToolCall:
    name: str
    input: dict[str, Any]
    books: list[int]  # 결과의 기관 도서 id, 결과 순서
    note: str | None

    @property
    def keywords(self) -> list[str]:
        return list(self.input.get("keywords") or [])

    @property
    def keyword_missing(self) -> bool:
        """검색 낱말이 있는데 키워드 순위가 비고 벡터 순위만 있었다."""
        return self.note == NO_KEYWORD_MATCH


@dataclass
class Capture:
    calls: list[ToolCall] = field(default_factory=list)

    def take(self) -> list[ToolCall]:
        taken, self.calls = self.calls, []
        return taken


def _wrap(tool: Tool, capture: Capture) -> Tool:
    async def handler(ctx: ToolContext, data: Any) -> Any:
        output = await tool.handler(ctx, data)
        books = output.get("books", []) if isinstance(output, dict) else []
        capture.calls.append(
            ToolCall(
                tool.name,
                data.model_dump(mode="json"),
                [b["library_book_id"] for b in books],
                output.get("note") if isinstance(output, dict) else None,
            )
        )
        return output

    return replace(tool, handler=handler)


def capturing(profile: Profile, capture: Capture) -> Profile:
    """책 tool을 감싼 프로필. 이름·설명·스키마·기록 필드는 그대로다."""
    tools = tuple(_wrap(t, capture) if t.name in CAPTURED_TOOLS else t for t in profile.tools)
    return replace(profile, tools=tools)
