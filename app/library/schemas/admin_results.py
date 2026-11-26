"""운영 에이전트의 결과 사건(SSE `result`) 모양. 화면용 변환(`Tool.present`)이 만든다.

지금 분석 결과 모델(`schemas/analytics.py`)과 따로 둔 화면용 모델이다. 표(`TableResult`)와 초안
링크(`DraftLink`) 두 종류이고 `kind`로 나눈다. 표의 칸은 일반 값이라, 회원 값이 들어가지 않는지는
열 허용 목록과 실제 값 테스트(`tests/library/test_admin_results_privacy.py`)가 지킨다.

`schemas/admin_agent.py`와 나눈 것은 그 모듈이 프로필(`admin_agent.py`)을 import하고, 프로필은
tool 파일을 import하기 때문이다(tool 파일이 이 모듈을 쓴다).
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_ROWS = 50  # 분석 목록 상한(`LIMIT_MAX`)과 같다

Cell = str | int | float | None


class TableResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["table"] = "table"
    title: str
    caption: str | None
    columns: list[str] = Field(min_length=1)
    rows: list[list[Cell]] = Field(max_length=MAX_ROWS)
    bar_column: int | None  # 막대를 그릴 숫자 열 번호
    total: int | None  # 잘린 목록의 전체 수
    truncated: bool

    @model_validator(mode="after")
    def _shape(self) -> Self:
        width = len(self.columns)
        if any(len(row) != width for row in self.rows):
            raise ValueError("행마다 칸 수가 열 수와 같아야 합니다")
        if self.bar_column is not None and not 0 <= self.bar_column < width:
            raise ValueError("막대 열 번호가 열 범위 밖입니다")
        return self


DraftKind = Literal["curation", "template", "purchase"]


class DraftLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["draft"] = "draft"
    draft: DraftKind
    id: int


ResultPayload = Annotated[TableResult | DraftLink, Field(discriminator="kind")]
