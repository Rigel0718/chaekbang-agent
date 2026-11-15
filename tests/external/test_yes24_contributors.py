"""[catalog/book-contributors] YES24 저자 표기 해석."""

import pytest

from app.central.external.yes24.contributors import parse_yes24_author
from app.core.contributors import ContributorRole

A, IL, T, S, OR, X = (
    ContributorRole.AUTHOR,
    ContributorRole.ILLUSTRATOR,
    ContributorRole.TRANSLATOR,
    ContributorRole.SUPERVISOR,
    ContributorRole.ORIGINAL,
    ContributorRole.OTHER,
)


def people(author: str) -> list[tuple[str, ContributorRole]]:
    return [(p.name, p.role) for p in parse_yes24_author(author)]


def test_story_pictures_translation() -> None:
    """[catalog/book-contributors] YES24 저자 표기 해석 / 글, 그림, 역"""
    assert people("칼 멜링 글/브라이트 스타 그림/김맑아,김경덕 역") == [
        ("칼 멜링", A),
        ("브라이트 스타", IL),
        ("김맑아", T),
        ("김경덕", T),
    ]


def test_original_and_supervisor() -> None:
    """[catalog/book-contributors] YES24 저자 표기 해석 / 원저와 감수"""
    assert people("흔한남매 원저/김언정,송은경 글/임혜영 그림/정현철 감수") == [
        ("흔한남매", OR),
        ("김언정", A),
        ("송은경", A),
        ("임혜영", IL),
        ("정현철", S),
    ]


def test_others_and_joint() -> None:
    """[catalog/book-contributors] YES24 저자 표기 해석 / 외, 등저, 공역"""
    assert people("정재은 외 글/박기종 외 그림") == [("정재은", A), ("박기종", IL)]
    assert people("강동화,강주은,김동천 등저") == [("강동화", A), ("강주은", A), ("김동천", A)]
    assert people("더글러스 애덤스 저/김선형,권진아 공역") == [
        ("더글러스 애덤스", A),
        ("김선형", T),
        ("권진아", T),
    ]


def test_name_with_parens() -> None:
    """[catalog/book-contributors] YES24 저자 표기 해석 / 괄호가 있는 이름"""
    assert people("에반(하상희) 저") == [("에반(하상희)", A)]


@pytest.mark.parametrize(
    ("author", "expected"),
    [
        ("유선혜 저", [("유선혜", A)]),
        ("김상근 글그림", [("김상근", A), ("김상근", IL)]),
        ("나가노 글,그림", [("나가노", A), ("나가노", IL)]),
        (
            "시바타 케이코 글그림/황진희 역",
            [("시바타 케이코", A), ("시바타 케이코", IL), ("황진희", T)],
        ),
        ("모죠 원작/서지원 글/김기수 그림", [("모죠", OR), ("서지원", A), ("김기수", IL)]),
        ("정재승 기획/정재은 글/김기수 그림", [("정재승", X), ("정재은", A), ("김기수", IL)]),
        (
            "무라카미 하루키 저/김진욱 역/안자이 미즈마루 그림/무라카미 요코 사진",
            [("무라카미 하루키", A), ("김진욱", T), ("안자이 미즈마루", IL), ("무라카미 요코", X)],
        ),
        ("밥 비엘,폴 스웨츠 공저/박영인 역", [("밥 비엘", A), ("폴 스웨츠", A), ("박영인", T)]),
        (
            "알랭 드 보통,인생학교 저/신인수 역",
            [("알랭 드 보통", A), ("인생학교", A), ("신인수", T)],
        ),
        ("동아사이언스 어린이과학동아편집부", [("동아사이언스 어린이과학동아편집부", A)]),
        (
            "사회평론 역사연구소,이지혜 글/정숭교 감수",
            [("사회평론 역사연구소", A), ("이지혜", A), ("정숭교", S)],
        ),
        (
            "Sumio Hataya 글그림/신혜선 역",
            [("Sumio Hataya", A), ("Sumio Hataya", IL), ("신혜선", T)],
        ),
        ("스와프나 해도우 글", [("스와프나 해도우", A)]),
        ("타블라라사 편집팀,이정기 공저", [("타블라라사 편집팀", A), ("이정기", A)]),
        # 실험 장서(2026-11-15)에서 처음 본 역할 표기
        (
            "레이 커즈와일 저/김명남,장시형 역/진대제 감수/정재승 해제",
            [("레이 커즈와일", A), ("김명남", T), ("장시형", T), ("진대제", S), ("정재승", X)],
        ),
    ],
)
def test_sample_shapes(author: str, expected: list) -> None:
    """표본에서 본 꼴마다 대표 표기(design Context)."""
    assert people(author) == expected


def test_role_text_kept() -> None:
    assert [p.role_text for p in parse_yes24_author("정재승 기획/정재은 글")] == ["기획", "글"]
    assert parse_yes24_author("동아사이언스")[0].role_text is None
