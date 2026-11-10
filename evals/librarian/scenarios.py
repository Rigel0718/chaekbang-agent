"""AI 사서 평가 시나리오. 항목마다 확인하는 스펙의 요구사항과 시나리오 이름을 적어 추적한다.

표본은 실제 YES24 서지지만 잡지, 수험서, 고등학습서가 섞여 있어 작은도서관 장서와 다르다. 그래서
주제 시나리오는 표본에 그 주제가 있을 만한 것으로 고르고, 기대는 조건으로 쓴다.
`{no_description_title}`은 적재한 표본에서 소개를 지운 책의 서명으로 바뀐다.
"""

from dataclasses import dataclass
from enum import StrEnum


class Expect(StrEnum):
    RECOMMEND = "recommend"  # 추천이 하나 이상
    NO_MATCH = "no_match"  # 추천이 없고 희망도서 안내 표시가 켜짐
    NO_DESCRIPTION = "no_description"  # 소개 정보가 없다고 답함
    ANY = "any"  # 규칙 검사만 본다


@dataclass(frozen=True)
class Scenario:
    id: str
    turns: tuple[str, ...]
    expect: Expect
    children: bool  # 코드의 어린이 요청 판단이 마지막 턴에서 이 값이어야 한다
    traces: tuple[str, ...]  # 확인하는 스펙 시나리오: "[capability] 요구사항 / 시나리오"
    topic: str | None = None  # 추천 중 하나 이상의 서지에 이 낱말이 있어야 한다


GENERAL_NO_PERSONAL = "[agent/librarian] 개인정보를 묻지 않음 / 일반 추천 대화"
CHILDREN_ONLY = "[features/children] 어린이 최종 검사 / 어린이 요청에 어린이 도서만 추천"

SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "dinosaur",
        ("공룡 책 추천해줘",),
        Expect.RECOMMEND,
        children=False,
        traces=("[agent/librarian] 소장 도서로 답함 / 공룡 책 추천", GENERAL_NO_PERSONAL),
        topic="공룡",
    ),
    Scenario(
        "child-dinosaur",
        ("7살 아이 공룡 책 있어요?",),
        Expect.ANY,
        children=True,
        traces=(CHILDREN_ONLY,),
    ),
    Scenario(
        "grandchild-picture-book",
        ("손주와 같이 읽을 그림책 추천해 주세요",),
        Expect.RECOMMEND,
        children=True,
        traces=(CHILDREN_ONLY,),
    ),
    Scenario(
        "elementary-science",
        ("초등학생이 볼 과학책 있나요?",),
        Expect.ANY,
        children=True,
        traces=(CHILDREN_ONLY,),
    ),
    Scenario(
        "not-held",
        ("양자 컴퓨터 회로 설계 전문서 있나요?",),
        Expect.NO_MATCH,
        children=False,
        traces=("[agent/librarian] 없는 책 안내 / 소장하지 않은 주제",),
    ),
    Scenario(
        "no-description",
        ("『{no_description_title}』은 어떤 내용이에요?",),
        Expect.NO_DESCRIPTION,
        children=False,
        traces=("[agent/librarian] 지어내지 않음 / 소개 없는 책 질문",),
    ),
    Scenario(
        "after-work-essay",
        ("퇴근 후 30분 읽을 에세이 추천해 주세요",),
        Expect.RECOMMEND,
        children=False,
        traces=(GENERAL_NO_PERSONAL,),
    ),
    Scenario(
        "cooking",
        ("집에서 간단히 해 먹을 요리책 있어요?",),
        Expect.RECOMMEND,
        children=False,
        traces=(GENERAL_NO_PERSONAL,),
    ),
    Scenario(
        "history",
        ("역사 쉽게 읽을 책 추천해 주세요",),
        Expect.ANY,
        children=False,
        traces=(GENERAL_NO_PERSONAL,),
    ),
    Scenario(
        "parenting",
        ("아이 훈육 방법 책 추천해 주세요",),
        Expect.ANY,
        children=False,  # 부모가 읽을 책. 어린이로 좁히면 오판이다
        traces=("[features/children] 어린이 요청 판단 / 부모가 읽을 책",),
    ),
    Scenario(
        "children-follow-up",
        ("7살 아이 책 추천해 주세요", "다른 건요?"),
        Expect.ANY,
        children=True,
        traces=("[features/children] 대화 안에서 유지 / 이어지는 질문", CHILDREN_ONLY),
    ),
    Scenario(
        "switch-to-adult",
        ("7살 아이 책 추천해 주세요", "이제 제가 읽을 소설요"),
        Expect.ANY,
        children=False,
        traces=("[features/children] 대화 안에서 유지 / 어른 책으로 전환",),
    ),
)
