"""[features/children] 판단 규칙 (값 표)."""

import pytest

from app.features.children.rules import (
    has_children_label,
    is_children_category,
    is_children_request,
)


@pytest.mark.parametrize("mark", ["아", "아동", "어린이", "유", "유아", "J", "j"])
def test_children_marks(mark: str) -> None:
    """[features/children] 파일 근거 / 별치기호로 분류"""
    assert has_children_label(mark, None, None)


@pytest.mark.parametrize("mark", ["참", "R", "향토", "아동문학연구", "청소년"])
def test_other_marks(mark: str) -> None:
    """[features/children] 파일 근거 (별치기호는 완전 일치만)"""
    assert not has_children_label(mark, None, None)


@pytest.mark.parametrize("shelf", ["어린이자료실", "어린이 자료실 1", "아동실", "유아방"])
def test_children_shelf(shelf: str) -> None:
    """[features/children] 파일 근거 / 자료실로 분류"""
    assert has_children_label(None, shelf, None)


def test_general_shelf() -> None:
    """[features/children] 파일 근거 / 근거가 없는 행"""
    assert not has_children_label(None, "일반 자료실", None)
    assert not has_children_label(None, None, None)


def test_addition_code() -> None:
    """[features/children] 파일 근거 / 부가기호로 분류"""
    assert has_children_label(None, None, "77810")


def test_elementary_study_addition_code() -> None:
    """[features/children] 파일 근거 / 초등 학습참고서 부가기호"""
    assert has_children_label(None, None, "63710")


@pytest.mark.parametrize("code", ["43810", "53710"])
def test_secondary_addition_codes(code: str) -> None:
    """[features/children] 파일 근거 / 중·고등 부가기호"""
    assert not has_children_label(None, None, code)


@pytest.mark.parametrize("mark", ["어", "c", "C"])
def test_unsourced_marks(mark: str) -> None:
    """[features/children] 파일 근거 / 출처가 없는 별치기호"""
    assert not has_children_label(mark, None, None)


@pytest.mark.parametrize("code", ["03810", "43810", "7781", "7781X", "778100"])
def test_other_addition_codes(code: str) -> None:
    """[features/children] 파일 근거 (청소년 4와 형식이 다른 값은 아님)"""
    assert not has_children_label(None, None, code)


@pytest.mark.parametrize("category", ["국내도서-유아", "국내도서-어린이", "국내도서-초등학습서"])
def test_children_categories(category: str) -> None:
    """[features/children] 외부 분류 근거 / 어린이 근거인 분류 (값 표)"""
    assert is_children_category(category)


@pytest.mark.parametrize(
    "category",
    [
        "국내도서-청소년",
        "국내도서-전집",
        "국내도서-중고등학습서-중학교",
        "국내도서-소설/시/희곡",
        "외국도서-어린이",
        "국내도서-어린이-문학",
        "",
        None,
    ],
)
def test_other_categories(category: str | None) -> None:
    """[features/children] 외부 분류 근거 / 어린이 근거가 아닌 분류 (값 표, 완전 일치만)"""
    assert not is_children_category(category)


# --- 어린이 요청 판단 ---


def test_request_age() -> None:
    """[features/children] 어린이 요청 판단 / 나이"""
    assert is_children_request(["7살 아이 공룡 책"])
    assert is_children_request(["일곱 살 공룡 책"])
    assert is_children_request(["18개월 아기 책"])
    assert is_children_request(["13세 추천 도서"])


@pytest.mark.parametrize(
    "text", ["손주와 같이 읽을 그림책", "초등 3학년 과학책", "어린이 공룡 책", "우리 애가 볼 책"]
)
def test_request_children_words(text: str) -> None:
    """[features/children] 어린이 요청 판단 / 대상 표현"""
    assert is_children_request([text])


@pytest.mark.parametrize(
    "text", ["아이디어 책", "딸기 요리책", "아들러 심리학 책", "아이돌 에세이", "아이폰 사용법"]
)
def test_request_similar_words(text: str) -> None:
    """[features/children] 어린이 요청 판단 / 비슷한 낱말"""
    assert not is_children_request([text])


@pytest.mark.parametrize("text", ["아이 훈육 방법 책", "육아 책 추천", "엄마가 읽을 아이 심리 책"])
def test_request_parent_books(text: str) -> None:
    """[features/children] 어린이 요청 판단 / 부모가 읽을 책"""
    assert not is_children_request([text])


@pytest.mark.parametrize("text", ["20살 아들이 읽을 소설", "15세 딸 선물", "중학생 아들 책"])
def test_request_teen_or_older(text: str) -> None:
    """[features/children] 어린이 요청 판단 / 14세 이상"""
    assert not is_children_request([text])


def test_request_other_texts() -> None:
    """[features/children] 어린이 요청 판단 (어린이 표현이 없으면 아님)"""
    assert not is_children_request(["공룡 책 추천해줘"])
    assert not is_children_request(["20세기 역사책"])
    assert not is_children_request([])


def test_request_kept_in_conversation() -> None:
    """[features/children] 대화 안에서 유지 / 이어지는 질문"""
    assert is_children_request(["7살 책", "다른 건요?"])
    assert is_children_request(["7살 책", "공룡은요?", "더 보여 줘"])


def test_request_released_by_adult() -> None:
    """[features/children] 대화 안에서 유지 / 어른 책으로 전환"""
    assert not is_children_request(["7살 책", "이제 제가 읽을 소설요"])
    assert is_children_request(["7살 책", "이제 제가 읽을 소설요", "다시 아이 책요"])


def test_request_reading_together() -> None:
    """[features/children] 대화 안에서 유지 / 함께 읽기"""
    assert is_children_request(["제가 아이랑 같이 읽을 책"])
    assert is_children_request(["어른이 아이와 함께 읽을 그림책"])
