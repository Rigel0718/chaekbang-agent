"""[catalog/book-contributors] 역할 표기 해석, 기관 파일 저자 표기 해석, 저자 키 규칙."""

import pytest

from app.core.contributors import Contributor, ContributorRole, author_keys, parse_author_text

A, IL, T, E, S, OR, X = (
    ContributorRole.AUTHOR,
    ContributorRole.ILLUSTRATOR,
    ContributorRole.TRANSLATOR,
    ContributorRole.EDITOR,
    ContributorRole.SUPERVISOR,
    ContributorRole.ORIGINAL,
    ContributorRole.OTHER,
)


def people(author: str) -> list[tuple[str, ContributorRole]]:
    return [(p.name, p.role) for p in parse_author_text(author)]


@pytest.mark.parametrize("author", ["김영하 저", "김영하 지음", "김영하 글", "김영하 (지은이)"])
def test_same_role_many_spellings(author: str) -> None:
    """[catalog/book-contributors] 역할 표기 해석 / 같은 역할의 여러 표기"""
    assert people(author) == [("김영하", A)]


def test_no_role_mark() -> None:
    """[catalog/book-contributors] 역할 표기 해석 / 역할 표기 없음"""
    assert parse_author_text("동아사이언스 어린이과학동아편집부") == [
        Contributor("동아사이언스 어린이과학동아편집부", A, None)
    ]


@pytest.mark.parametrize(
    "author", ["김상근 글그림", "김상근 글,그림", "김상근 글·그림", "김상근 글, 그림"]
)
def test_story_and_pictures(author: str) -> None:
    """[catalog/book-contributors] 역할 표기 해석 / 글과 그림을 함께"""
    assert people(author) == [("김상근", A), ("김상근", IL)]


def test_other_role() -> None:
    """[catalog/book-contributors] 역할 표기 해석 / 그 밖의 역할"""
    assert parse_author_text("정재승 기획") == [Contributor("정재승", X, "기획")]


def test_unknown_role_label() -> None:
    """[catalog/book-contributors] 역할 표기 해석 / 표에 없는 표기"""
    assert parse_author_text("낭독자: 김소리") == [Contributor("김소리", X, "낭독자")]


def test_role_words_table() -> None:
    """역할 표의 대표 표기. 앞의 `공`·`등`은 역할에 붙는 말이다."""
    assert people("김 편") == [("김", E)]
    assert people("홍길동 엮음") == [("홍길동", E)]
    assert people("정현철 감수") == [("정현철", S)]
    assert people("흔한남매 원저") == [("흔한남매", OR)]
    assert people("모죠 원작") == [("모죠", OR)]
    assert people("김선형,권진아 공역") == [("김선형", T), ("권진아", T)]
    assert people("강동화,강주은 등저") == [("강동화", A), ("강주은", A)]
    assert parse_author_text("김선형 공역")[0].role_text == "공역"


def test_label_form() -> None:
    """[catalog/book-contributors] 기관 파일 저자 표기 해석 / 이름표 꼴"""
    assert people("지은이: 한강; 옮긴이: 데보라 스미스") == [("한강", A), ("데보라 스미스", T)]


def test_paren_form() -> None:
    """[catalog/book-contributors] 기관 파일 저자 표기 해석 / 괄호 꼴"""
    assert people("백희나 (지은이), 김소연 (옮긴이)") == [("백희나", A), ("김소연", T)]


def test_name_only() -> None:
    """[catalog/book-contributors] 기관 파일 저자 표기 해석 / 이름만"""
    assert parse_author_text("김주민") == [Contributor("김주민", A, None)]


def test_other_shapes() -> None:
    """기관 파일의 다른 꼴: `;`·`|` 묶음, 끝 낱말, 괄호가 역할이 아닌 이름, 쉼표로 나뉜 지은이."""
    assert people("한 강 지음 ; 데보라 스미스 옮김") == [("한 강", A), ("데보라 스미스", T)]
    assert people("김영하 | 이현 그림") == [("김영하", A), ("이현", IL)]
    assert people("에반(하상희)") == [("에반(하상희)", A)]
    assert people("박마을, 김주민") == [("박마을", A), ("김주민", A)]
    assert people("칼 멜링 글/브라이트 스타 그림/김맑아,김경덕 역") == [
        ("칼 멜링", A),
        ("브라이트 스타", IL),
        ("김맑아", T),
        ("김경덕", T),
    ]


def test_unreadable_shape_is_one_author() -> None:
    """읽을 수 없는 꼴은 원문 전체가 `author` 한 명이다. 기호뿐이면 아무도 없다."""
    assert people("  ") == []
    assert people("- / -") == []
    assert people("(주)") == [("(주)", A)]


def test_author_keys() -> None:
    """[catalog/book-contributors] 기관 도서 저자 키 (규칙): 지은이·원저만, 중복 없이."""
    assert author_keys("한 강 지음 ; 데보라 스미스 옮김") == ["한강"]
    assert author_keys("흔한남매 원저/김언정,송은경 글/임혜영 그림/정현철 감수") == [
        "흔한남매",
        "김언정",
        "송은경",
    ]
    assert author_keys("김상근 글그림") == ["김상근"]
    assert author_keys("홍길동 역") == []
    assert author_keys("J.K. Rowling") == ["jkrowling"]
    assert author_keys(None) == []
