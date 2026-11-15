"""실험 장서의 분야 구성 (design 결정 12). 목표 525권, 거르고 나면 약 500권.

받는 순서대로 적는다. 하위 카테고리(시/희곡, 청소년 문학)를 상위보다 먼저 받아 중복이 하위
분야에 남게 한다. `holdout`인 분야는 받아서 장서에 넣되 `add-recommendation-experiments`의 평가
세트와 조정에 쓰지 않는다(`add-bibliographic-sources`의 "다른 분야" 비교에서 처음 쓴다).
서가 위치는 가상 기관의 사본에 넣는 값이고, 어린이 구분의 근거가 된다(ISBN 없는 책).
"""

from dataclasses import dataclass

GENERAL_SHELF = "일반 자료실"


@dataclass(frozen=True)
class Field:
    key: str
    name: str
    category_id: str
    target: int
    holdout: bool = False
    shelf: str = GENERAL_SHELF


FIELDS: tuple[Field, ...] = (
    Field("poetry", "시/희곡", "001001046014", 15),
    Field("teen_fiction", "청소년 문학", "001001005004", 30, shelf="청소년 서가"),
    Field("toddler", "유아", "001001027", 75, shelf="유아 자료실"),
    Field("children", "어린이", "001001016", 95, shelf="어린이 자료실"),
    Field("fiction", "소설/시/희곡", "001001046", 40),
    Field("essay", "에세이", "001001047", 30),
    Field("humanities", "인문", "001001019", 25),
    Field("society", "사회 정치", "001001022", 20),
    Field("economy", "경제 경영", "001001025", 25),
    Field("self_help", "자기계발", "001001026", 20),
    Field("science", "자연과학", "001001002", 25),
    Field("history", "역사", "001001010", 25),
    Field("comics", "만화/라이트노벨", "001001008", 20),
    Field("it", "IT 모바일", "001001003", 15),
    Field("home", "가정 살림", "001001001", 15),
    Field("religion", "종교", "001001021", 10, holdout=True),
    Field("art", "예술", "001001007", 15, holdout=True),
    Field("health", "건강 취미", "001001011", 15, holdout=True),
    Field("travel", "여행", "001001009", 10, holdout=True),
)

FIELDS_BY_KEY = {field.key: field for field in FIELDS}
