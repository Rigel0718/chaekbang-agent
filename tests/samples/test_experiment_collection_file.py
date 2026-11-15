"""실험 장서 파일 전체 확인(`evals/collection/data/yes24_collection.json`). 파일이 없으면 건너뛴다.

역할별 건수는 고정하지 않는다(87권 표본 테스트가 고정한다).
남는 역할 표기가 있으면 역할 표에 더한다.
"""

import json

import pytest

from app.central.external.yes24.contributors import parse_yes24_author
from app.central.external.yes24.parsing import parse_item
from app.core.contributors import ROLE_WORDS
from app.core.text import match_key
from evals.collection.fetch import DATA_FILE, skip_reason

pytestmark = pytest.mark.skipif(not DATA_FILE.exists(), reason=f"실험 장서가 없습니다: {DATA_FILE}")


@pytest.fixture(scope="module")
def items() -> list[dict]:
    document = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    return [row["item"] for row in document["books"]]


def test_every_item_is_a_book(items: list[dict]) -> None:
    """[platform/experiment-collection] 분야 구성대로 받기

    받은 파일 전체가 거르기 규칙을 지난다.
    """
    assert items
    for item in items:
        parsed = parse_item(item)
        assert skip_reason(item) is None, parsed.isbn13
        assert parsed.title and parsed.author


def test_every_book_has_contributor(items: list[dict]) -> None:
    """[catalog/book-contributors] YES24 저자 표기 해석 (실험 장서 전체)"""
    empty = [item["author"] for item in items if not parse_yes24_author(item["author"])]
    assert empty == []


def test_no_role_mark_left_in_names(items: list[dict]) -> None:
    """[catalog/book-contributors] YES24 저자 표기 해석

    실험 장서: 이름에 붙어 남은 역할 표기가 없다.
    """
    left = []
    for item in items:
        for person in parse_yes24_author(item["author"]):
            last = match_key(person.name.split(" ")[-1])
            # 이름이 `외`로 끝나거나(`김참외`) 역할 낱말로 시작할 수 있어(`편집부`)
            # 끝 낱말 전체로 본다
            stuck = last[-1:] in ("외", "등") and last[:-1] in ROLE_WORDS  # `저외`
            if last in ROLE_WORDS or last in ("외", "등") or stuck:
                left.append((item["author"], person.name))
    assert left == []
