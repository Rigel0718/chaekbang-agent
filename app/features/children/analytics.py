"""어린이 분석 축: 운영 에이전트의 장서·대출 분석에 어린이·일반 구분을 더한다.

그 기관에서 어린이 도서로 구분된 책만 `children`에 배정하고, 구분이 없거나 확실하지 않은 책은
기본값 `general`로 센다(설계 원칙 4와 같은 방향). 결과의 `general`은 "어린이로 분류되지 않음"이다.
`general`로 저장된 행도 기본값과 같아 배정에서 뺀다.
"""

from sqlalchemy import Select, literal, select

from app.features.children.models import Audience
from app.features.children.service import children_book_ids
from app.library.admin_agent import AdminExtension
from app.library.analytics.axes import AnalysisAxis

AXIS_NAME = "audience"


def _assign(library_id: int) -> Select:
    ids = children_book_ids(library_id).subquery()
    return select(ids.c.library_book_id, literal(Audience.CHILDREN.value).label("value"))


AUDIENCE_AXIS = AnalysisAxis(
    name=AXIS_NAME,
    description=(
        "어린이·일반 구분. children은 이 도서관에서 어린이 도서(영유아·초등)로 분류된 책, "
        "general은 어린이로 분류되지 않은 책(분류가 확실하지 않은 책 포함)"
    ),
    values=(Audience.CHILDREN.value, Audience.GENERAL.value),
    default=Audience.GENERAL.value,
    labels={
        Audience.CHILDREN.value: "어린이",
        Audience.GENERAL.value: "어린이로 분류되지 않음",
    },
    assign=_assign,
)


ADMIN_PROMPT_NOTE = """\
어린이 도서
- 아동, 어린이, 아이, 유아, 초등, 그림책, 동화 책을 물으면 audience=children으로 거르거나 묶는다. \
어른 책, 일반 책을 물으면 audience=general이다.
- children은 이 도서관에서 어린이 도서로 분류한 책이다. 답에 "이 도서관의 어린이 도서 분류 \
기준"임을 밝힌다. general은 어린이로 분류되지 않은 책이고, 분류가 확실하지 않은 책도 들어간다.
- "아동 과학책"은 audience=children과 fields=[자연과학]이다.
"""


def admin_extension() -> AdminExtension:
    return AdminExtension(axes=(AUDIENCE_AXIS,), prompt_note=ADMIN_PROMPT_NOTE)
