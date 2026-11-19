"""분석 축: 기관 개별 기능이 더하는 책의 구분(예: 어린이·일반).

공통 분석은 축의 이름을 부르지 않는다. 기능이 축을 만들어 운영 에이전트 조립(`AdminExtension`)에
넘기면, 그 이름이 장서 현황·대출 통계의 묶기 값과 네 분석의 필터가 된다. 축이 없으면 tool 입력에도
없다.

`assign`은 기본값이 아닌 값으로 배정된 책만 `(library_book_id, value)`로 돌려준다. 배정이 없는 책은
기본값으로 센다. 같은 책을 두 번 배정하지 않는다.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from sqlalchemy import Select


@dataclass(frozen=True)
class AnalysisAxis:
    name: str  # tool 입력의 묶기 값이자 필터 필드 이름
    description: str  # tool 입력 설명
    values: tuple[str, ...]
    default: str
    labels: Mapping[str, str]  # 결과에 보이는 이름
    assign: Callable[[int], Select]  # library_id → (library_book_id, value)

    def __post_init__(self) -> None:
        if self.default not in self.values:
            raise ValueError(f"{self.name}: 기본값 {self.default}이 값 목록에 없습니다")
        if set(self.labels) != set(self.values):
            raise ValueError(f"{self.name}: 표시 이름이 값 목록과 다릅니다")
