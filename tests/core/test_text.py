"""글자 정규화 규칙. Python과 PostgreSQL이 같은 결과를 내는지 실제 DB에서 본다."""

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
)

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
]


@pytest.mark.parametrize("value", SAMPLES)
async def test_compact_same_in_python_and_sql(session: AsyncSession, value: str) -> None:
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
]


@pytest.mark.parametrize("value", JAMO_SAMPLES)
async def test_jamo_same_in_python_and_sql(session: AsyncSession, value: str) -> None:
    """[platform/database-schema] 마이그레이션으로 스키마 생성 / 자모 분해 규칙 일치"""
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
