"""글자 정규화 규칙. Python과 PostgreSQL이 같은 결과를 내는지 실제 DB에서 본다."""

import pytest
from sqlalchemy import literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.text import clean_spaces, compact, compact_sql

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
