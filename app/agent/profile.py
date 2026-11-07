"""프로필: 프롬프트, tool 묶음, 최종 답, 최종 검사, 한도. 조립은 app/main.py가 한다.

최종 검사는 훅과 다르다. 훅은 사건을 알리고, 검사는 판정해서 답을 막는다.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import AnswerTool, Tool, ToolInput


@dataclass(frozen=True)
class Violation:
    message: str  # LLM에 돌려주는 설명. 기록에 남기지 않는다
    items: tuple[Any, ...] = ()  # 위반 항목 값. 기록에 남는다


@dataclass(frozen=True)
class CheckContext:
    library_id: int
    session: AsyncSession
    user_texts: tuple[str, ...]  # 이번 실행까지의 이용자 문장
    tool_names: tuple[str, ...]  # 이번 실행에서 호출한 tool


class FinalCheck(Protocol):
    name: str

    async def check(self, ctx: CheckContext, answer: Any) -> list[Violation]: ...


@dataclass(frozen=True)
class Profile:
    name: str
    version: str
    system_prompt: str
    tools: tuple[Tool, ...]
    answer_tool: AnswerTool
    fallback_answer: ToolInput  # 검사를 거치지 않는 고정 답. 책을 넣지 않는다
    final_checks: tuple[FinalCheck, ...] = ()
    # 위반 항목을 뺀 답을 돌려준다. 뺄 수 없으면 None이다.
    repair: Callable[[Any, Sequence[Violation]], Any | None] | None = None
    max_llm_calls: int = 8
    max_check_retries: int = 2

    def __post_init__(self) -> None:
        names = [tool.name for tool in self.tools] + [self.answer_tool.name]
        if len(names) != len(set(names)):
            raise ValueError(f"{self.name}: tool 이름이 겹칩니다: {names}")
