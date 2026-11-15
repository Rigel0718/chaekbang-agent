"""글자 정규화 규칙. Python과 PostgreSQL이 같은 결과를 내는지 실제 DB에서 본다."""

import unicodedata

import pytest
from sqlalchemy import literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.text import (
    clean_spaces,
    compact,
    compact_sql,
    jamo,
    jamo_spaced,
    jamo_sql,
    jamo_starts,
    jamo_starts_sql,
    kdc_key,
    match_key,
    strip_edition,
)


def nfd(value: str) -> str:
    return unicodedata.normalize("NFD", value)


# 공백 종류(일반, 탭, 줄바꿈, 줄바꿈 없는 공백, 전각, em, 폭 없는 공백, BOM)와 대소문자가 섞인 값
SAMPLES = [
    "공룡 백과",
    "공룡\t백과\n2권",
    "공룡 백과",
    "공룡　백과",
    "공룡 백과",
    "공룡​백과",
    "﻿공룡 백과",
    "Dinosaur ATLAS",
    "  앞뒤  공백  ",
    "100% 즐기는_여행",
    "",
    # 전각, 분해형 한글(NFD)
    "ＡＢＣ１２３ 살인사건",
    "Ｃ＋＋ ｆｉｒｓｔ",
    nfd("공룡 백과"),
    nfd("괜찮아 닭볶음탕") + " ＶＯＬ．２",
]


@pytest.mark.parametrize("value", SAMPLES)
async def test_compact_same_in_python_and_sql(session: AsyncSession, value: str) -> None:
    """[platform/text-normalization] 코드와 SQL의 일치 / 비교용 키 일치"""
    in_sql = await session.scalar(select(compact_sql(literal(value))))
    assert in_sql == compact(value)


async def test_compact_sql_null(session: AsyncSession) -> None:
    assert await session.scalar(select(compact_sql(literal(None)))) == ""


def test_compact() -> None:
    assert compact("공룡 백과") == "공룡백과"
    assert compact("공룡​ 백 과") == "공룡백과"
    assert compact("Dinosaur ATLAS") == "dinosauratlas"


def test_clean_spaces() -> None:
    assert clean_spaces("  공룡  백과\t2권 ") == "공룡 백과 2권"
    assert clean_spaces("공룡​백과") == "공룡백과"  # 보이지 않는 글자는 공백이 아니라 지운다
    assert clean_spaces("﻿등록번호") == "등록번호"


# 겹받침, 이중 모음, 조합 중인 자모, 된소리, 영문, 숫자, 기호, 공백 종류가 섞인 값
JAMO_SAMPLES = [
    "데미안",
    "괜찮아 닭볶음탕",
    "읽기 싫은 값 없음",
    "데미ㅇ",
    "그림ㅊ",
    "ㅘ ㄳ ㅢ ㄲ",
    "꽃밭에서 뛰어놀자",
    "Dinosaur ATLAS 3권",
    "100% 즐기는_여행",
    "  앞뒤  공백\t2권 ",
    "공룡​백과",
    "",
    # 판본·묶음 표기
    "진짜 진짜 재밌는 공룡 그림책 (완전판)",
    "[예스리커버] 아는 만큼 보인다",
    "작고 귀엽고 사라지는 것들 (친필 사인본) + 엽서 3종",
    "EBS 수능특강 사회·문화 (2026년) (2027 수능대비",
    "어린이과학동아 (격주간) : 21호 (11/1) [2026]",
    "(주)",
    "[ ]",
    "C++ 첫걸음",
    "괄호)만 닫힘",
    # 전각, 분해형 한글(NFD)
    "ＡＢＣ 살인사건",
    "１９８４",
    nfd("데미안"),
    nfd("진짜 진짜 공룡 그림책 (완전판)"),
    "Ｃ＋＋ 첫걸음 （개정판）",
]


@pytest.mark.parametrize("value", JAMO_SAMPLES)
async def test_jamo_same_in_python_and_sql(session: AsyncSession, value: str) -> None:
    """[platform/database-schema] 마이그레이션으로 스키마 생성 / 자모 분해 규칙 일치
    [platform/text-normalization] 코드와 SQL의 일치 / 자모 키 일치"""
    assert await session.scalar(select(jamo_sql(literal(value)))) == jamo(value)
    assert await session.scalar(select(jamo_starts_sql(literal(value)))) == jamo_starts(value)


async def test_jamo_sql_null(session: AsyncSession) -> None:
    assert await session.scalar(select(jamo_sql(literal(None)))) == ""
    assert await session.scalar(select(jamo_starts_sql(literal(None)))) is None


def test_jamo_syllables() -> None:
    assert jamo("데미안") == "ㄷㅔㅁㅣㅇㅏㄴ"
    assert jamo("데미 안") == "ㄷㅔㅁㅣㅇㅏㄴ"  # 공백은 지운다
    assert jamo("Dino") == "dino"


def test_jamo_compounds() -> None:
    """겹받침과 이중 모음은 나누고, 된소리는 둔다."""
    assert jamo("닭") == "ㄷㅏㄹㄱ"
    assert jamo("괜") == "ㄱㅗㅐㄴ"
    assert jamo("의") == "ㅇㅡㅣ"
    assert jamo("꽃") == "ㄲㅗㅊ"


def test_jamo_composing_input() -> None:
    """조합 중인 입력은 완성된 서명의 앞부분이 된다."""
    assert jamo("데미안").startswith(jamo("데미ㅇ"))
    assert jamo("관찰").startswith(jamo("고"))
    assert jamo("관찰").startswith(jamo("ㄱㅘ"))
    assert jamo("ㄳ") == "ㄱㅅ"


def test_jamo_spaced() -> None:
    assert jamo_spaced("  진짜 진짜  그림책 ") == "ㅈㅣㄴㅉㅏ ㅈㅣㄴㅉㅏ ㄱㅡㄹㅣㅁㅊㅐㄱ"
    assert jamo_spaced("Dino ATLAS") == "dino atlas"


def test_jamo_starts() -> None:
    """낱말마다 그 낱말부터 끝까지 이은 키. 첫 값이 `jamo`다."""
    assert jamo_starts("최소한의 한국사") == [jamo("최소한의한국사"), jamo("한국사")]
    assert jamo_starts("  데미안 ") == [jamo("데미안")]
    assert jamo_starts("") == []
    assert jamo_starts("   ") == []


def test_strip_edition() -> None:
    """[catalog/book-lookup] 판본·묶음 표기 무시 (규칙)"""
    assert strip_edition("진짜 진짜 재밌는 공룡 그림책 (완전판)") == "진짜 진짜 재밌는 공룡 그림책"
    assert strip_edition("[예스리커버] 아는 만큼 보인다") == "아는 만큼 보인다"
    assert strip_edition("작고 귀엽고 사라지는 것들 (친필 사인본) + 엽서 3종") == (
        "작고 귀엽고 사라지는 것들"
    )
    assert (
        strip_edition("EBS 수능특강 사회·문화 (2026년) (2027 수능대비") == "EBS 수능특강 사회·문화"
    )
    assert strip_edition("(주)") == "(주)"  # 지워서 비면 원래 서명
    assert strip_edition("C++ 첫걸음") == "C++ 첫걸음"
    assert strip_edition("  데미안 ") == "데미안"
    assert jamo_starts("최소한의 한국사 (개정판)") == [jamo("최소한의한국사"), jamo("한국사")]


# --- platform/text-normalization ---


def test_clean_spaces_rules() -> None:
    """[platform/text-normalization] 저장용 정규화 / 공백 정리"""
    assert clean_spaces("  공룡  백과\t2권 ") == "공룡 백과 2권"


def test_clean_spaces_nfc() -> None:
    """[platform/text-normalization] 저장용 정규화 / 분해형 한글"""
    decomposed = nfd("김영하")
    assert decomposed != "김영하"
    assert clean_spaces(decomposed) == "김영하"


def test_clean_spaces_keeps_marks() -> None:
    """[platform/text-normalization] 저장용 정규화 / 표기는 그대로"""
    assert clean_spaces("J.K. Rowling") == "J.K. Rowling"
    assert clean_spaces("ＡＢＣ") == "ＡＢＣ"  # 전각은 저장할 때 바꾸지 않는다


def test_compact_spacing_and_case() -> None:
    """[platform/text-normalization] 비교용 정규화 / 띄어쓰기와 대소문자"""
    assert compact("Dinosaur ATLAS") == compact("dinosauratlas")


def test_compact_fullwidth() -> None:
    """[platform/text-normalization] 비교용 정규화 / 전각 글자"""
    assert compact("ＡＢＣ１２３") == compact("abc123") == "abc123"


def test_compact_nfd() -> None:
    """[platform/text-normalization] 비교용 정규화 / 분해형 한글"""
    assert compact(nfd("공룡 백과")) == compact("공룡백과")


def test_compact_keeps_compatibility_jamo() -> None:
    """[platform/text-normalization] 비교용 정규화 / 조합 중인 자모는 그대로"""
    assert compact("데미ㅇ") == "데미ㅇ"
    assert jamo("데미안").startswith(jamo("데미ㅇ"))


def test_match_key_spaced_name() -> None:
    """[platform/text-normalization] 이름 맞춤 키 / 띄어 쓴 이름"""
    assert match_key("김 영 하") == match_key("김영하") == "김영하"


def test_match_key_marks_and_case() -> None:
    """[platform/text-normalization] 이름 맞춤 키 / 마침표와 대소문자"""
    assert match_key("J.K. Rowling") == match_key("j.k.rowling") == "jkrowling"


def test_match_key_series() -> None:
    """[platform/text-normalization] 이름 맞춤 키 / 시리즈명"""
    assert match_key("민음사 세계문학전집") == match_key("민음사  세계문학전집")


def test_match_key_transliteration() -> None:
    """[platform/text-normalization] 이름 맞춤 키 / 음역이 다른 이름"""
    assert match_key("조앤 K. 롤링") != match_key("J.K. 롤링")


def test_match_key_symbols_only() -> None:
    """[platform/text-normalization] 이름 맞춤 키 / 기호뿐인 값"""
    assert match_key("-") == ""
    assert match_key(" · ") == ""


def test_kdc_key_same_value() -> None:
    """[platform/text-normalization] KDC 키 / 표기가 달라도 같은 값"""
    for value in ("813.7", "KDC 813.7", "８１３．７", "813.7-한232ㅊ", " 813.7 "):
        assert kdc_key(value) == "813.7", value


def test_kdc_key_without_fraction() -> None:
    """[platform/text-normalization] KDC 키 / 소수점 없는 값"""
    assert kdc_key("813") == kdc_key("813.") == "813"


def test_kdc_key_unreadable() -> None:
    """[platform/text-normalization] KDC 키 / 읽을 수 없는 값"""
    for value in ("문학", "81", "아 813", "8131", "", None):
        assert kdc_key(value) is None, value
