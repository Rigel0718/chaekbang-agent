"""테스트에서 DB에 직접 쓰는 도우미. API·service를 거치지 않고 저장 계층 제약을 확인할 때 쓴다."""

from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

# 체크 디지트가 올바른 ISBN-13
VALID_ISBN = "9780306406157"
VALID_ISBN_2 = "9791162203620"
VALID_ISBN_3 = "9788932917245"


async def insert(session: AsyncSession, table: str, **values: Any) -> Any:
    """raw SQL INSERT 후 RETURNING *의 행을 돌려준다."""
    cols = ", ".join(values)
    params = ", ".join(f":{k}" for k in values)
    result = await session.execute(
        text(f"INSERT INTO {table} ({cols}) VALUES ({params}) RETURNING *"), values
    )
    return result.mappings().one()


async def assert_sql_rejected(session: AsyncSession, sql: str, **params: Any) -> None:
    """DB가 SQL 실행을 거부하는지 확인한다. 실패한 문장은 savepoint로 되돌린다."""
    savepoint = await session.begin_nested()
    with pytest.raises(DBAPIError):
        await session.execute(text(sql), params)
    await savepoint.rollback()


async def assert_rejected(session: AsyncSession, table: str, **values: Any) -> None:
    """DB가 INSERT를 거부하는지 확인한다."""
    cols = ", ".join(values)
    params = ", ".join(f":{k}" for k in values)
    await assert_sql_rejected(session, f"INSERT INTO {table} ({cols}) VALUES ({params})", **values)


async def add_book(session: AsyncSession, isbn: str = VALID_ISBN, **overrides: Any) -> Any:
    values = {"isbn": isbn, "title": "테스트 도서", "author": "테스트 저자", "list_price": 15000}
    values.update(overrides)
    return await insert(session, "books", **values)


async def add_institution(session: AsyncSession, **overrides: Any) -> Any:
    values = {"name": "햇살어린이집", "type": "daycare"}
    values.update(overrides)
    return await insert(session, "institutions", **values)
