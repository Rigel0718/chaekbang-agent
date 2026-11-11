"""AI 사서 평가 시나리오. 항목마다 확인하는 스펙의 요구사항과 시나리오 이름을 적어 추적한다.

표본은 실제 YES24 서지지만 잡지, 수험서, 고등학습서가 섞여 있어 작은도서관 장서와 다르다. 그래서
주제 시나리오는 표본에 그 주제가 있을 만한 것으로 고르고, 기대는 조건으로 쓴다.
`{no_description_title}`은 적재한 표본에서 소개를 지운 책의 서명으로, `{shelved_title}`은 서가
위치를 따로 둔 책의 서명으로 바뀐다.

안내 시나리오(`Expect.GUIDE`)는 평가 안내(`evals/librarian/guide.py`)와 고정한 날짜(2026-11-11
수요일 14:00)를 기준으로 쓴다. `contains`의 항목은 모두 답에 있어야 하고, 튜플 항목은 그중 하나만
있으면 된다.
"""

from dataclasses import dataclass
from enum import StrEnum


class Expect(StrEnum):
    RECOMMEND = "recommend"  # 추천이 하나 이상
    NO_MATCH = "no_match"  # 추천이 없고 희망도서 안내 표시가 켜짐
    NO_DESCRIPTION = "no_description"  # 소개 정보가 없다고 답함
    ANY = "any"  # 규칙 검사만 본다
    GUIDE = "guide"  # 답 문장이 contains를 모두 담고 absent를 담지 않음


class GuideSetup(StrEnum):
    FULL = "full"  # 평가 안내를 넣는다
    EMPTY = "empty"  # 안내를 등록하지 않은 기관


@dataclass(frozen=True)
class Scenario:
    id: str
    turns: tuple[str, ...]
    expect: Expect
    children: bool  # 코드의 어린이 요청 판단이 마지막 턴에서 이 값이어야 한다
    traces: tuple[str, ...]  # 확인하는 스펙 시나리오: "[capability] 요구사항 / 시나리오"
    topic: str | None = None  # 추천 중 하나 이상의 서지에 이 낱말이 있어야 한다
    guide: GuideSetup = GuideSetup.FULL
    contains: tuple[str | tuple[str, ...], ...] = ()  # 답 문장에 있어야 할 값. 튜플은 그중 하나
    absent: tuple[str, ...] = ()  # 답 문장에 없어야 할 정규식
    searches_books: bool = False  # 안내 시나리오 중 책을 찾아야 답할 수 있는 것(지표에서 뺀다)


GENERAL_NO_PERSONAL = "[agent/librarian] 개인정보를 묻지 않음 / 일반 추천 대화"
CHILDREN_ONLY = "[features/children] 어린이 최종 검사 / 어린이 요청에 어린이 도서만 추천"
GUIDE_ANSWER = "[agent/librarian] 등록된 안내로 답함"
GUIDE_UNKNOWN = "[agent/librarian] 등록되지 않은 안내는 지어내지 않음"
GUIDE_PHONE = "031-000-0000"  # evals/librarian/guide.py의 가상 대표 연락처
TIME_PATTERN = r"\d{1,2}\s*시|\d{1,2}:\d{2}"

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
    Scenario(
        "guide-hours",
        ("오늘 몇 시까지 해요?",),
        Expect.GUIDE,
        children=False,
        traces=(f"{GUIDE_ANSWER} / 오늘 운영 시간", GENERAL_NO_PERSONAL),
        contains=(("18", "6시"),),
    ),
    Scenario(
        "guide-closed-day",
        ("월요일에도 열어요?",),
        Expect.GUIDE,
        children=False,
        traces=(f"{GUIDE_ANSWER} / 정기 휴관 질문",),
        contains=(("휴관", "쉬", "닫"),),
    ),
    Scenario(
        "guide-due-date",
        ("오늘 빌리면 언제까지 갖다줘야 해요?",),
        Expect.GUIDE,
        children=False,
        traces=(f"{GUIDE_ANSWER} / 반납 예정일 질문",),
        contains=("11월 26일",),
    ),
    Scenario(
        "guide-toilet",
        ("화장실 어디예요?",),
        Expect.GUIDE,
        children=False,
        traces=(f"{GUIDE_ANSWER} / 시설 위치",),
        contains=("1층",),
    ),
    Scenario(
        "guide-loan-limit",
        ("몇 권까지 빌릴 수 있어요?",),
        Expect.GUIDE,
        children=False,
        traces=(f"{GUIDE_ANSWER} / 대출 권수",),
        contains=("5권",),
    ),
    Scenario(
        "guide-contact",
        ("담당자 연락처 알려 주세요",),
        Expect.GUIDE,
        children=False,
        traces=(f"{GUIDE_ANSWER} / 연락처",),
        contains=(GUIDE_PHONE,),
    ),
    Scenario(
        "guide-unregistered",
        ("와이파이 비밀번호 뭐예요?",),
        Expect.GUIDE,
        children=False,
        traces=(f"{GUIDE_UNKNOWN} / 등록되지 않은 질문",),
        contains=(GUIDE_PHONE,),
    ),
    Scenario(
        "guide-empty-hours",
        ("몇 시까지 해요?",),
        Expect.GUIDE,
        children=False,
        traces=(f"{GUIDE_UNKNOWN} / 빈 안내의 운영 시간",),
        guide=GuideSetup.EMPTY,
        contains=(("담당자", "문의"),),
        absent=(TIME_PATTERN,),
    ),
    Scenario(
        "guide-my-loans",
        ("제가 빌린 책 언제까지예요?",),
        Expect.GUIDE,
        children=False,
        traces=(f"{GUIDE_UNKNOWN} / 본인 대출 질문", GENERAL_NO_PERSONAL),
        contains=(("데스크", "담당자", GUIDE_PHONE),),
    ),
    Scenario(
        "guide-book-location",
        ("『{shelved_title}』 어디 있어요?",),
        Expect.GUIDE,
        children=False,
        traces=(f"{GUIDE_ANSWER} / 책 위치",),
        contains=("2층",),
        searches_books=True,
    ),
    Scenario(
        "guide-mixed",
        ("공룡 책 있어요? 그리고 토요일에도 열어요?",),
        Expect.GUIDE,
        children=False,
        traces=(GENERAL_NO_PERSONAL,),
        topic="공룡",
        contains=(("13", "1시"),),
        searches_books=True,
    ),
)
