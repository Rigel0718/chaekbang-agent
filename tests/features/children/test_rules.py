"""[features/children] 판단 규칙 (값 표)."""

import pytest

from app.features.children.rules import has_children_label, is_children_category


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
