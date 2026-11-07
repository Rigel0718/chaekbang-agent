"""tool 계약. 이름, 설명, 입력 스키마, 실행 함수로 정의하고 실행기와 같은 프로세스에서 돈다.

입력 모델은 ToolInput을 상속한다. 정의되지 않은 값을 받지 않으므로 LLM은 library_id를 넣을 수 없고,
기관은 실행기가 ToolContext로 주입한다. strict 스키마는 모든 필드를 필수로 요구해서 기본값을 쓰지
않는다. 값이 없어도 되는 필드는 `T | None`으로 둔다.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession


class ToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class ToolContext:
    library_id: int
    session: AsyncSession


@dataclass(frozen=True)
class ToolSpec:
    """LLM에 넘기는 정의. MCP의 tool 정의와 모양이 같다."""

    name: str
    description: str
    parameters: dict[str, Any]


def _spec(name: str, description: str, input_model: type[ToolInput]) -> ToolSpec:
    return ToolSpec(name, description, input_model.model_json_schema())


def _require_all_fields(name: str, input_model: type[ToolInput]) -> None:
    optional = [k for k, field in input_model.model_fields.items() if not field.is_required()]
    if optional:
        raise ValueError(f"{name}: 입력 필드에 기본값을 쓸 수 없습니다: {optional}")


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[ToolInput]
    handler: Callable[[ToolContext, Any], Awaitable[str | dict[str, Any] | list[Any]]]
    status_label: str  # 이용자에게 보이는 진행 문구
    record_fields: tuple[str, ...] = ()  # 실행 기록에 남겨도 되는 입력 필드

    def __post_init__(self) -> None:
        _require_all_fields(self.name, self.input_model)

    @property
    def spec(self) -> ToolSpec:
        return _spec(self.name, self.description, self.input_model)


@dataclass(frozen=True)
class AnswerTool:
    """최종 답. 실행 함수가 없고, 입력 모델이 곧 답의 구조다."""

    name: str
    description: str
    input_model: type[ToolInput]

    def __post_init__(self) -> None:
        _require_all_fields(self.name, self.input_model)

    @property
    def spec(self) -> ToolSpec:
        return _spec(self.name, self.description, self.input_model)
