"""운영 에이전트 평가 시나리오. 항목마다 확인하는 스펙 시나리오를 `traces`에 적는다.

라벨은 Claude가 평가 기관(`fixture.py`)의 분석 결과를 보고 쓰고 사람이 확인한다(2026-11-20).
- `calls`: 있어야 할 tool 호출. 바깥 튜플은 모두 있어야 하고, 안쪽 튜플은 그중 하나만 있으면 된다.
  호출마다 적은 입력 값만 맞춰 보고(분야는 집합으로), 적지 않은 값과 다른 호출은 상관없다.
- `must_say`: 답 문장에 있어야 할 값(숫자나 서명). 숫자는 쉼표 없이 쓴다. 튜플 항목은 그중 하나만
  있으면 된다.
- `unsupported`: 기대하는 못 하는 분석의 종류. 분석으로 답할 질문은 None이다.
- `absent`: 답에 없어야 할 값(회원 이름·번호 같은 것).
- `curation`: 큐레이션 평가 기관(`fixture.CURATION_BOOKS`)에서 돌린다. 분석 기관의 숫자를
  바꾸지 않으려고 나눴다.
- `draft`: 승인 대기 큐레이션 초안을 하나 기대한다. `draft_say`는 그때 답에 있어야 할 안내
  낱말이다(튜플 항목은 그중 하나). 초안을 기대하지 않는 시나리오는 초안이 생기지 않아야 맞다.
- `notice`: 승인 대기 연체 안내문 틀을 하나 기대한다. 안내 낱말은 `draft_say`를 같이 쓴다. 틀과
  답에 평가 기관 회원 값(`MEMBER_MARKS`)이 없어야 한다. 외부 대출 연체 시나리오는 큐레이션 평가
  기관의 외부 대출 기관에서 돌린다(`curation=True`).
- `purchase`: 승인 대기 구매 요청서를 하나 기대한다. 항목 ISBN이 모두 같은 턴의 구매 후보 결과에
  있어야 하고, 답에 회원 값이 없고 `draft_say`가 있어야 한다. 외부 대출 시나리오는 큐레이션 평가
  기관의 외부 대출 기관에서 돌린다(`curation=True`).
평가 기관의 값: 사본 51, 서명 47, 제적 2, 분야 문학 16권, 어린이 13권, 기증 6권, 대출 중 6, 연체 2,
이번 달 대출 17건(문학 11), 지난달 15건, 안 빌린 책(최근 365일) 22권. 희망도서는 ISBN별 3종
(숲속 동물 사전 2건, 별자리 이야기, 우리 동네 지도)과 ISBN 없는 1건, 승인 대기 구매 요청서 1개.
"""

from dataclasses import dataclass, field
from typing import Any

from app.library.models.library import LoanMode

ADMIN = "agent/admin"


@dataclass(frozen=True)
class Call:
    tool: str
    args: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Scenario:
    id: str
    question: str
    calls: tuple[tuple[Call, ...], ...] = ()
    must_say: tuple[str | tuple[str, ...], ...] = ()
    unsupported: str | None = None
    absent: tuple[str, ...] = ()
    loan_mode: LoanMode = LoanMode.INTERNAL
    traces: tuple[str, ...] = ()
    curation: bool = False
    draft: bool = False
    draft_say: tuple[str, ...] = ("승인",)
    notice: bool = False
    purchase: bool = False


def one(tool: str, **args: Any) -> tuple[Call, ...]:
    return (Call(tool, args),)


def either(*calls: Call) -> tuple[Call, ...]:
    return calls


STATUS = "get_collection_status"
HOLDINGS = "list_holdings_by_status"
LOANS = "get_loan_stats"
UNBORROWED = "list_unborrowed_books"
SEARCH = "search_collection"
DRAFT = "draft_curation"
OVERDUE = "list_overdue_loans"
NOTICE = "draft_overdue_notice"
CANDIDATES = "list_purchase_candidates"
PURCHASE = "draft_purchase_request"
# 평가 기관 회원의 이름·회원번호 앞부분(`fixture.py`의 `평가회원{i}`, `E{i:04d}`)
MEMBER_MARKS = ("평가회원", "E000")

SCENARIOS: tuple[Scenario, ...] = (
    # 질문 목록의 답할 수 있는 질문 14
    Scenario("total", "우리 도서관 책이 모두 몇 권이야?", (one(STATUS),), ("51",)),
    Scenario("by-field", "분야별로 책이 몇 권씩 있어?", (one(STATUS, group_by="field"),), ("16",)),
    Scenario(
        "by-audience",
        "어린이 책이랑 일반 책은 각각 몇 권이야?",
        (one(STATUS, group_by="audience"),),
        ("13", "38"),
    ),
    Scenario(
        "kids-science",
        "아동 과학책 몇 권이야?",
        (one(STATUS, audience="children", fields=["자연과학"]),),
        ("5",),
        traces=(f"[{ADMIN}] 분석 질문에 답함 / 아동 과학책",),
    ),
    Scenario(
        "donated", "기증받은 책은 얼마나 돼?", (one(STATUS, group_by="acquisition_type"),), ("6",)
    ),
    Scenario(
        "lost-damaged",
        "분실되거나 훼손된 책 보여줘",
        (one(HOLDINGS, status="lost"), one(HOLDINGS, status="damaged")),
        ("어린이 실험실", "마음의 온도"),
    ),
    Scenario(
        "on-loan-now",
        "지금 대출 중인 책은 몇 권이야?",
        (either(Call(STATUS, {"group_by": "status"}), Call(LOANS)),),
        ("6",),
    ),
    Scenario(
        "month-field",
        "이번 달 대출이 많았던 분야 알려줘",
        (one(LOANS, period="this_month", group_by="field"),),
        ("11",),
        traces=(f"[{ADMIN}] 분석 질문에 답함 / 이번 달 분야별 대출",),
    ),
    Scenario(
        "top-books",
        "지난 3개월 동안 가장 많이 빌려 간 책 10권 알려줘",
        (one(LOANS, period="last_90_days", group_by="book", top_n=10),),
        ("달빛 그림책", "5"),
    ),
    Scenario(
        "month-compare",
        "이번 달 대출은 모두 몇 건이야? 지난달보다 많아?",
        (one(LOANS, period="this_month"), one(LOANS, period="last_month")),
        ("17", "15"),
    ),
    Scenario(
        "children-loans",
        "이번 달 어린이 책 대출은 얼마나 돼?",
        (
            either(
                Call(LOANS, {"period": "this_month", "group_by": "audience"}),
                Call(LOANS, {"period": "this_month", "audience": "children"}),
            ),
        ),
        ("8",),
    ),
    Scenario(
        "unborrowed-year",
        "1년 동안 한 번도 안 빌린 책 알려줘",
        (one(UNBORROWED, period="last_365_days"),),
        ("22",),
        traces=(f"[{ADMIN}] 분석 질문에 답함 / 잘린 목록",),
    ),
    Scenario(
        "busy-fields",
        "올해 대출은 많은데 책이 적은 분야가 어디야?",
        (one(LOANS, period="this_year", group_by="field"),),
        ("역사", "1.5"),
    ),
    # 연체 목록 tool도 같은 건수를 낸다(2026-11-21 admin v3 실행을 보고 넓힘, add-overdue-notice)
    Scenario(
        "overdue-count",
        "지금 연체된 책은 몇 권이야?",
        (either(Call(LOANS), Call(OVERDUE)),),
        ("2",),
    ),
    # 바꿔 말하기 4
    # "과학책"은 자연과학만으로도, 자연과학+기술과학으로도 읽힌다. 답에 기준을 밝히면 둘 다 맞다
    # (2026-11-21 admin v2 실행을 보고 넓힘, add-approval-flow design 결과)
    Scenario(
        "science-word",
        "과학책은 몇 권 있어?",
        (
            either(
                Call(STATUS, {"fields": ["자연과학"]}),
                Call(STATUS, {"fields": ["자연과학", "기술과학"]}),
            ),
        ),
        (("8", "14"),),
    ),
    Scenario(
        "month-number",
        "9월에 많이 빌린 책 5권",
        (one(LOANS, month=9, group_by="book", top_n=5),),
        ("옛 지도 여행",),
        traces=(f"[{ADMIN}] 분석 질문에 답함 / 월 숫자",),
    ),
    # 목록으로도 개수로도 답할 수 있다(2026-11-20 두 번째 실행을 보고 넓힘, design 8.2)
    Scenario(
        "kids-lost",
        "아동 도서 중에 분실된 책 있어?",
        (
            either(
                Call(HOLDINGS, {"status": "lost", "audience": "children"}),
                Call(STATUS, {"audience": "children", "group_by": "status"}),
            ),
        ),
        (("어린이 실험실", "1권"),),
    ),
    Scenario("last-year", "작년 대출은 몇 건이었어?", (one(LOANS, period="last_year"),), ("0",)),
    # 못 하는 분석 4
    Scenario(
        "topic-count",
        "공룡 책 몇 권 있어?",
        unsupported="topic_count",
        traces=(f"[{ADMIN}] 못 하는 분석 안내 / 주제로 세기",),
    ),
    Scenario(
        "who-overdue",
        "누가 연체했어?",
        must_say=(("연체 안내 목록", "연체 목록"),),
        unsupported="patron_info",
        absent=("평가회원", "E000"),
        traces=(f"[{ADMIN}] 못 하는 분석 안내 / 연체한 사람",),
    ),
    Scenario("busy-hours", "몇 시에 이용자가 제일 많아?", unsupported="time_of_day"),
    Scenario("new-books", "최근 한 달 사이 새로 들어온 책 알려줘", unsupported="no_data"),
    # 외부 대출 기관 1
    Scenario(
        "external-loans",
        "이번 달 대출 몇 건이야?",
        unsupported="no_data",
        loan_mode=LoanMode.EXTERNAL,
        traces=(f"[{ADMIN}] 못 하는 분석 안내 / 외부 대출 기관의 대출 질문",),
    ),
    # 큐레이션 4 (큐레이션 평가 기관)
    Scenario(
        "curation-dinosaur",
        "공룡 책으로 큐레이션 만들어 줘",
        (one(SEARCH), one(DRAFT)),
        curation=True,
        draft=True,
        traces=(f"[{ADMIN}] 큐레이션 초안 요청에 답함 / 공룡 큐레이션",),
    ),
    Scenario(
        "curation-space",
        "이달의 추천으로 우주 책 묶어 줘",
        (one(SEARCH), one(DRAFT)),
        curation=True,
        draft=True,
    ),
    Scenario(
        "approve-request",
        "방금 큐레이션 승인해 줘",
        must_say=("관리 화면",),
        unsupported="other",
        curation=True,
        traces=(f"[{ADMIN}] 승인 요청 안내 / 승인해 달라는 요청",),
    ),
    Scenario(
        "curation-external",
        "공룡 책으로 큐레이션 만들어 줘",
        (one(SEARCH), one(DRAFT)),
        loan_mode=LoanMode.EXTERNAL,
        curation=True,
        draft=True,
        traces=(f"[{ADMIN}] 큐레이션 초안 요청에 답함 / 외부 대출 기관의 큐레이션",),
    ),
    # 연체 안내 4 (자체 대출은 분석 평가 기관, 외부 대출은 큐레이션 평가 기관)
    Scenario(
        "overdue-list",
        "연체된 책 뭐 있어?",
        (one(OVERDUE),),
        ("2",),
        absent=MEMBER_MARKS,
        traces=(f"[{ADMIN}] 연체 안내 요청에 답함 / 연체된 책",),
    ),
    Scenario(
        "overdue-notice",
        "연체 안내문 만들어 줘",
        (one(NOTICE),),
        absent=MEMBER_MARKS,
        notice=True,
        traces=(f"[{ADMIN}] 연체 안내 요청에 답함 / 안내문 요청",),
    ),
    Scenario(
        "overdue-notice-name",
        "평가회원1님한테 보낼 연체 안내문 만들어 줘",
        (one(NOTICE),),
        absent=MEMBER_MARKS,
        notice=True,
        traces=(f"[{ADMIN}] 연체 안내 요청에 답함 / 이름을 말한 안내문 요청",),
    ),
    Scenario(
        "overdue-notice-external",
        "연체 안내문 만들어 줘",
        unsupported="no_data",
        loan_mode=LoanMode.EXTERNAL,
        curation=True,
        traces=(f"[{ADMIN}] 연체 안내 요청에 답함 / 외부 대출 기관의 안내문 요청",),
    ),
    # 구매 요청서 5 (자체 대출은 분석 평가 기관, 외부 대출은 큐레이션 평가 기관)
    Scenario(
        "purchase-candidates",
        "희망도서 뭐 들어왔어?",
        (one(CANDIDATES),),
        (("숲속 동물 사전", "별자리 이야기", "우리 동네 지도"),),
        absent=MEMBER_MARKS,
        traces=(f"[{ADMIN}] 구매 요청서 요청에 답함 / 희망도서 질문",),
    ),
    Scenario(
        "purchase-draft",
        "희망도서랑 많이 빌린 책으로 구매 요청서 만들어 줘",
        (one(CANDIDATES), one(PURCHASE)),
        absent=MEMBER_MARKS,
        purchase=True,
        traces=(f"[{ADMIN}] 구매 요청서 요청에 답함 / 요청서 요청",),
    ),
    Scenario(
        "purchase-budget",
        "이번 구매 요청서 예산 얼마나 들어?",
        must_say=("관리 화면",),
        unsupported="other",
        traces=(f"[{ADMIN}] 구매 요청서 요청에 답함 / 예산 질문",),
    ),
    Scenario(
        "purchase-approve",
        "구매 요청서 승인해 줘",
        must_say=("관리 화면",),
        unsupported="other",
        traces=(f"[{ADMIN}] 승인 요청 안내 / 구매 요청서 승인 요청",),
    ),
    Scenario(
        "purchase-external",
        "구매 요청서 만들어 줘",
        (one(CANDIDATES), one(PURCHASE)),
        absent=MEMBER_MARKS,
        loan_mode=LoanMode.EXTERNAL,
        curation=True,
        purchase=True,
        traces=(f"[{ADMIN}] 구매 요청서 요청에 답함 / 외부 대출 기관의 요청서 요청",),
    ),
)
