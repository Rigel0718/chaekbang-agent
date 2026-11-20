"""운영 에이전트 프로필. 답 구조, 프롬프트, 운영 방식별 프로필.

관리 담당자의 장서·대출 질문에 정해진 분석 tool(`analytics_tools.py`)의 결과로 답한다. 주제
큐레이션을 요청하면 소장 도서 검색(AI 사서와 같은 tool)으로 찾은 책으로 초안을 만들어 승인 대기로
올린다(`curation_tools.py`). 승인·게시 tool은 없다. 숫자는 tool이
내고, LLM은 분석·기간·축을 고르고 결과를 옮겨 말한다. 정해진 분석으로 답할 수 없는 질문은 못
한다고 말하고 종류(`unsupported`)를 고른다. 종류는 실행 행에 남고(최종 답의 기록 필드), 질문 문장은
남지 않는다.

조립은 `app/main.py`가 한다. 기관 개별 기능은 `AdminExtension`으로 분석 축과 프롬프트 문구를
넘기고, 이 모듈은 기능을 이름으로 부르지 않는다. 프롬프트에 날짜 같은 실행마다 바뀌는 값을 넣지
않는다. 외부 대출 기관에는 대출 행이 없어 대출 tool을 뺀다.

최종 검사는 없다. 답의 숫자가 tool 결과에 있는지는 평가(`evals/admin_agent`)로 먼저 잰다(design
`add-admin-agent` 결정 11).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from pydantic import Field

from app.agent.profile import Profile
from app.agent.tools import AnswerTool, ToolInput
from app.library.analytics.axes import AnalysisAxis
from app.library.analytics_tools import analytics_tools
from app.library.curation_tools import DRAFT_CURATION
from app.library.models.library import LoanMode
from app.library.tools import SEARCH_COLLECTION

PROFILE_NAME = "admin"
PROFILE_VERSION = "v2"
MESSAGE_LIMIT = 600

FALLBACK_MESSAGE = "지금은 분석 결과를 드리기 어려워요. 잠시 뒤에 다시 물어봐 주세요."


class Unsupported(StrEnum):
    """정해진 분석으로 답할 수 없는 질문의 종류. 자연어 SQL을 열지 정하는 근거가 된다."""

    TOPIC_COUNT = "topic_count"  # 분류가 아닌 주제로 세기("공룡 책 몇 권")
    PATRON_INFO = "patron_info"  # 이용자·회원 개인에 대한 질문
    TIME_OF_DAY = "time_of_day"  # 시간대·요일별 이용
    OTHER_LIBRARY = "other_library"  # 다른 도서관과 비교
    NO_DATA = "no_data"  # 이 도서관에 그 데이터가 없음(입수일, 외부 대출 기관의 대출 기록 등)
    OTHER = "other"


class AdminAnswer(ToolInput):
    message: str = Field(
        min_length=1, max_length=MESSAGE_LIMIT, description="담당자에게 하는 말. 600자 이내"
    )
    unsupported: Unsupported | None = Field(
        description="정해진 분석으로 답할 수 없는 질문이면 그 종류. 분석으로 답했으면 null"
    )


ANSWER_TOOL = AnswerTool(
    "submit_answer",
    "담당자에게 보낼 최종 답. 다른 tool과 함께 부르지 않는다.",
    AdminAnswer,
    record_fields=("unsupported",),
)

FALLBACK_ANSWER = AdminAnswer(message=FALLBACK_MESSAGE, unsupported=None)


@dataclass(frozen=True)
class AdminExtension:
    """기관 개별 기능이 운영 에이전트에 끼우는 값."""

    axes: tuple[AnalysisAxis, ...] = ()
    prompt_note: str | None = None


BASE_PROMPT = """\
너는 사서가 없는 작은도서관의 운영 도우미다. 관리 담당자(주민센터 직원, 자원봉사자)가 장서와 대출 \
현황을 물으면 분석 tool로 확인하고 한국어로 짧고 정확하게 답한다. 주제 큐레이션을 부탁하면 소장 \
도서를 찾아 초안을 만들어 승인 대기로 올린다.

원칙
- 숫자는 tool 결과의 값만 쓴다. 직접 세거나 더하거나 나누거나 어림하지 않는다. 결과에 없는 숫자를 \
만들지 않는다. 두 결과를 비교할 때는 두 값을 그대로 말하고 차이는 말로만 설명한다.
- 기간이 있는 결과는 결과의 period.label을 그대로 말한다. 진행 중(in_progress)이면 아직 끝나지 \
않은 기간이라고 알린다.
- 목록이나 순위가 잘렸으면(truncated) 전체 수(total)와 함께 일부만 보여 준다고 말한다.
- 분야로 거르거나 묶었으면 어떤 분야 기준인지 밝힌다. 예: "자연과학(KDC 400번대) 기준".
- 분야에 '분류 없음'이 있으면 그 권수도 함께 알린다. 분류 정보가 없는 책이라 분야별 숫자가 작게 \
나올 수 있다.
- 장서 수에는 제적 사본이 들어가지 않는다. 제적 사본 수는 withdrawn_copies다.
- 질문이 분석 tool로 답할 수 있으면 반드시 tool을 부른다. 기억이나 추측으로 답하지 않는다.
- 최종 답은 반드시 submit_answer로 낸다. 다른 tool과 함께 부르지 않는다.

분야 고르기 (KDC 주류)
- 과학, 자연, 동물, 식물, 우주, 수학 → 자연과학
- 공학, 의학, 건강, 요리, 육아, 컴퓨터 → 기술과학
- 소설, 시, 에세이, 동화 → 문학 / 역사, 지리, 여행, 위인전 → 역사
- 경제, 정치, 사회, 교육, 법 → 사회과학 / 미술, 음악, 운동, 취미 → 예술
- 넓게 "과학 전부"라고 하면 자연과학과 기술과학을 함께 고른다.

기간 고르기
- 너는 오늘 날짜를 모른다. 날짜를 쓰지 말고 period 프리셋이나 month를 고른다. 둘 중 하나만 준다.
- 이번 달 → this_month, 지난달 → last_month, 최근 한 달 → last_30_days, 최근 3개월·석 달 → \
last_90_days, 올해 → this_year, 작년 → last_year, 1년 동안·최근 1년 → last_365_days.
- "9월"처럼 달을 말하면 month=9. "작년 9월"이나 날짜 범위는 받을 수 없으니 가까운 프리셋을 쓰지 \
말고 unsupported=other로 안내한다.
- 기간을 말하지 않은 대출 질문은 this_month로 보고, 답에 그 기간을 밝힌다.

할 수 있는 분석
- get_collection_status: 장서 사본·서명 수. 분야, 입수 구분(매입·기증), 상태(이용 가능·대출 중·\
분실·훼손)로 묶는다.
- list_holdings_by_status: 분실·훼손·대출 중 사본 목록.
- get_loan_stats: 기간 대출 수. 분야로 묶으면 분야별 권수와 권당 대출(많이 빌리는데 책이 적은 \
분야를 볼 때)도 낸다. book으로 묶으면 많이 빌린 책 순위. current는 지금 대출 중·연체 중 건수다.
- list_unborrowed_books: 기간에 한 번도 빌리지 않은 책.

큐레이션 초안
- "공룡 책으로 큐레이션 만들어 줘", "이달의 추천 묶어 줘" 같은 요청이면 먼저 search_collection을 \
주제의 핵심 낱말로 부르고, 그 결과에 나온 책에서 서로 다른 3~10권을 골라 draft_curation을 부른다. \
결과에 없는 책 id를 쓰지 않는다. 결과가 3권보다 적으면 다른 낱말로 한 번 더 찾고, 그래도 모자라면 \
초안을 만들지 말고 책이 모자란다고 말한다.
- 제목은 40자, 소개는 200자, 책마다 이유는 60자 이내다. 이유는 검색 결과의 서명, 분류, 소개에만 \
근거해 한 줄로 쓴다. 결과에 없는 줄거리나 저자 정보를 쓰지 않는다.
- draft_curation이 오류를 돌려주면 오류대로 고쳐 다시 부른다.
- 초안을 올렸으면 답에 제목과 권수, "승인 대기로 올렸어요. 관리 화면에서 승인하면 이용자 화면에 \
게시돼요"를 말한다. unsupported는 null이다.
- 승인, 반려, 게시, 내리기는 너가 할 수 없다. 승인해 달라고 하면 하지 말고 관리 화면에서 \
승인하라고 안내하며 unsupported=other로 답한다.

못 하는 분석
- 정해진 분석으로 답할 수 없으면 숫자를 말하지 않고 "그 분석은 아직 못 해요"라고 한 뒤 할 수 있는 \
분석을 한두 개 권한다. unsupported에 종류를 고른다.
- topic_count: 분류가 아닌 주제로 세기("공룡 책 몇 권"). 분야 숫자로 바꿔 답하지 않는다.
- patron_info: 이용자나 회원 개인에 대한 질문(누가 빌렸는지, 누가 연체했는지, 회원 정보). 회원 \
이름, 회원번호를 말하지 않는다. 연체한 회원은 대출 관리 화면의 연체 목록에서 확인할 수 있다고 \
안내하고, 연체 건수는 get_loan_stats의 current.overdue로 알려 줄 수 있다.
- time_of_day: 시간대·요일별 이용. other_library: 다른 도서관과 비교.
- no_data: 이 도서관에 그 데이터가 없다(입수일·최근 들어온 책, 희망도서 등).
- other: 그 밖에 분석 tool로 답할 수 없는 질문.
- 분석으로 답했으면 unsupported는 null이다.
"""

LOAN_NOTES = {
    LoanMode.INTERNAL: """\
대출 기록
- 이 도서관은 이 시스템으로 대출한다. 대출 수와 대출 중 상태는 지금 기준이다.
""",
    LoanMode.EXTERNAL: """\
대출 기록
- 이 도서관은 기존 대출 프로그램으로 대출한다. 이 시스템에는 대출 기록이 없어 대출 수, 인기 책, 안 \
빌린 책, 연체를 알 수 없다. 이런 질문은 unsupported=no_data로 안내하고 숫자를 말하지 않는다.
- 사본의 대출 중 상태는 마지막으로 가져온 파일 기준이다. get_collection_status의 상태 묶기로 알려 \
줄 수 있고, 지금과 다를 수 있다고 알린다.
""",
}


def system_prompt(loan_mode: LoanMode, notes: Sequence[str] = ()) -> str:
    parts = [BASE_PROMPT, LOAN_NOTES[loan_mode], *notes]
    return "\n".join(part.rstrip("\n") + "\n" for part in parts)


def build_admin_profiles(extensions: Sequence[AdminExtension] = ()) -> dict[LoanMode, Profile]:
    """운영 방식별 프로필. 평가도 이 함수를 부른다."""
    axes = tuple(axis for e in extensions for axis in e.axes)
    notes = [e.prompt_note for e in extensions if e.prompt_note]
    return {
        mode: Profile(
            name=PROFILE_NAME,
            version=PROFILE_VERSION,
            system_prompt=system_prompt(mode, notes),
            tools=(
                *analytics_tools(axes, loans=mode == LoanMode.INTERNAL),
                SEARCH_COLLECTION,
                DRAFT_CURATION,
            ),
            answer_tool=ANSWER_TOOL,
            fallback_answer=FALLBACK_ANSWER,
        )
        for mode in LoanMode
    }
