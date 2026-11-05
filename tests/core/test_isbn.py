"""ISBN 정규화·검증 함수 테스트 (catalog/books: ISBN 형식 정규화와 검증)."""

import pytest

from app.core.isbn import InvalidIsbnError, isbn13_check_digit, normalize_isbn


@pytest.mark.parametrize(
    "raw", ["978-0-306-40615-7", "978 0 306 40615 7", "9780306406157", " 978-0306406157 "]
)
def test_normalize_removes_hyphens_and_spaces(raw: str) -> None:
    assert normalize_isbn(raw) == "9780306406157"


@pytest.mark.parametrize("raw", ["0306406152", "97803064061X7", "978030640615", "abc", ""])
def test_rejects_wrong_length_or_non_digit(raw: str) -> None:
    with pytest.raises(InvalidIsbnError, match="13자리"):
        normalize_isbn(raw)


def test_rejects_wrong_check_digit() -> None:
    with pytest.raises(InvalidIsbnError, match="체크 디지트"):
        normalize_isbn("9780306406158")


@pytest.mark.parametrize(
    ("first12", "digit"), [("978030640615", "7"), ("979116220362", "0"), ("978893291724", "5")]
)
def test_check_digit(first12: str, digit: str) -> None:
    assert isbn13_check_digit(first12) == digit
