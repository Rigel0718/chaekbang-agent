"""[catalog/library-books] 외부 분류 근거 (값 표)."""

import pytest

from app.services.audience import is_children_category


@pytest.mark.parametrize("category", ["국내도서-유아", "국내도서-어린이", "국내도서-초등학습서"])
def test_children_categories(category: str) -> None:
    """[catalog/library-books] 외부 분류 근거 / 어린이 근거인 분류 (값 표)"""
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
    """[catalog/library-books] 외부 분류 근거 / 어린이 근거가 아닌 분류 (값 표, 완전 일치만)"""
    assert not is_children_category(category)
