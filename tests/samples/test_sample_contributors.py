"""표본 87권의 저자 표기 전체 해석. 표본을 다시 받으면 역할별 건수를 고친다."""

from collections import Counter

from app.central.external.yes24.contributors import parse_yes24_author
from app.core.contributors import ROLE_WORDS
from app.core.text import match_key
from evals.librarian.catalog import Sample

# 2026-11-07에 받은 표본의 역할별 건수
ROLE_COUNTS = {
    "author": 105,
    "illustrator": 30,
    "translator": 23,
    "supervisor": 7,
    "original": 2,
    "other": 3,
}


def test_every_book_has_contributor(sample: Sample) -> None:
    """[catalog/book-contributors] YES24 저자 표기 해석 (표본 전체)"""
    for row in sample.books:
        assert parse_yes24_author(row["author"]), row["author"]


def test_no_role_mark_left_in_names(sample: Sample) -> None:
    """이름 끝 낱말에 역할 표기가 붙어 남은 것이 없다. 남으면 역할 표에 더한다."""
    left = []
    for row in sample.books:
        for person in parse_yes24_author(row["author"]):
            last = match_key(person.name.split(" ")[-1])
            if (
                last in ROLE_WORDS
                or last.rstrip("외등") in ROLE_WORDS
                or last.endswith(("외", "등"))
            ):
                left.append((row["author"], person.name))
    assert left == []


def test_role_counts(sample: Sample) -> None:
    counts = Counter(p.role.value for r in sample.books for p in parse_yes24_author(r["author"]))
    assert counts == ROLE_COUNTS
