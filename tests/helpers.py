"""테스트에서 DB에 직접 쓰는 도우미.

API·service를 거치지 않고 데이터를 준비하거나 저장 계층 제약을 확인할 때 쓴다.
"""

from datetime import date, timedelta
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.isbn import isbn13_check_digit
from app.core.security import hash_password, hash_token, new_token

# 체크 디지트가 올바른 ISBN-13
VALID_ISBN = "9780306406157"
VALID_ISBN_2 = "9791162203620"
VALID_ISBN_3 = "9788932917245"

TEST_PASSWORD = "test-password-1"


def make_isbn(n: int) -> str:
    """n마다 다른, 체크 디지트가 올바른 ISBN-13."""
    first12 = f"979110000{n:03d}"
    return first12 + isbn13_check_digit(first12)


async def insert(session: AsyncSession, table: str, **values: Any) -> Any:
    """raw SQL INSERT 후 RETURNING *의 행을 돌려준다."""
    cols = ", ".join(values)
    params = ", ".join(f":{k}" for k in values)
    result = await session.execute(
        text(f"INSERT INTO {table} ({cols}) VALUES ({params}) RETURNING *"), values
    )
    return result.mappings().one()


async def fetch(session: AsyncSession, table: str, id: int) -> Any:
    result = await session.execute(text(f"SELECT * FROM {table} WHERE id = :id"), {"id": id})
    return result.mappings().one_or_none()


async def assert_sql_rejected(
    session: AsyncSession,
    sql: str,
    *,
    match: str | None = None,
    error: type[Exception] = IntegrityError,
    **params: Any,
) -> None:
    """DB가 SQL 실행을 제약 위반으로 거부하는지 확인한다. 실패한 문장은 savepoint로 되돌린다.

    값의 타입이 틀려 드라이버에서 실패하는 경우와 구분하려고 IntegrityError(제약 위반)만 인정한다.
    match를 주면 오류 메시지(제약 이름 등)에 그 문자열이 있어야 한다.
    """
    savepoint = await session.begin_nested()
    with pytest.raises(error, match=match):
        await session.execute(text(sql), params)
    await savepoint.rollback()


async def assert_rejected(
    session: AsyncSession,
    table: str,
    *,
    match: str | None = None,
    error: type[Exception] = IntegrityError,
    **values: Any,
) -> None:
    """DB가 INSERT를 제약 위반으로 거부하는지 확인한다."""
    cols = ", ".join(values)
    params = ", ".join(f":{k}" for k in values)
    await assert_sql_rejected(
        session,
        f"INSERT INTO {table} ({cols}) VALUES ({params})",
        match=match,
        error=error,
        **values,
    )


async def add_library(session: AsyncSession, **overrides: Any) -> Any:
    values = {
        "name": "테스트 작은도서관",
        "type": "small_library",
        "loan_mode": "internal",
        "default_loan_days": 14,
    }
    values.update(overrides)
    return await insert(session, "libraries", **values)


async def add_staff(
    session: AsyncSession,
    library_id: int,
    login_id: str,
    role: str = "admin",
    password: str = TEST_PASSWORD,
    **overrides: Any,
) -> Any:
    values = {
        "library_id": library_id,
        "login_id": login_id,
        "password_hash": hash_password(password),
        "role": role,
    }
    values.update(overrides)
    return await insert(session, "staff_users", **values)


async def add_staff_session(
    session: AsyncSession, staff: Any, *, expires_in: timedelta = timedelta(hours=1)
) -> str:
    """직원 세션을 직접 만들고 토큰 원문을 돌려준다."""
    token = new_token()
    await insert(
        session,
        "staff_sessions",
        library_id=staff["library_id"],
        staff_user_id=staff["id"],
        token_hash=hash_token(token),
        expires_at=clock.now() + expires_in,
    )
    return token


async def add_book(session: AsyncSession, isbn: str | None = VALID_ISBN, **overrides: Any) -> Any:
    values = {"isbn": isbn, "title": "테스트 도서", "author": "테스트 저자", "list_price": 15000}
    values.update(overrides)
    return await insert(session, "books", **values)


async def add_library_book(
    session: AsyncSession, library_id: int, isbn: str | None = VALID_ISBN, **overrides: Any
) -> Any:
    values = {
        "library_id": library_id,
        "isbn": isbn,
        "title": "테스트 도서",
        "author": "테스트 저자",
        "list_price": 15000,
    }
    values.update(overrides)
    return await insert(session, "library_books", **values)


async def add_holding(
    session: AsyncSession,
    library_id: int,
    library_book_id: int,
    accession_number: str,
    **overrides: Any,
) -> Any:
    values = {
        "library_id": library_id,
        "library_book_id": library_book_id,
        "accession_number": accession_number,
        "acquisition_type": "purchased",
        "purchase_price": 13500,
    }
    values.update(overrides)
    return await insert(session, "holdings", **values)


async def add_member(
    session: AsyncSession, library_id: int, member_number: str, name: str = "김이용"
) -> Any:
    return await insert(
        session, "members", library_id=library_id, member_number=member_number, name=name
    )


async def add_loan(
    session: AsyncSession,
    holding: Any,
    member: Any,
    *,
    loaned_on: date | None = None,
    due_on: date | None = None,
    returned_on: date | None = None,
) -> Any:
    """대출 행을 직접 만든다. 반납 안 된 대출이면 사본 상태도 on_loan으로 맞춘다."""
    loaned_on = loaned_on or clock.today()
    loan = await insert(
        session,
        "loans",
        library_id=holding["library_id"],
        holding_id=holding["id"],
        member_id=member["id"],
        loaned_on=loaned_on,
        due_on=due_on or loaned_on + timedelta(days=14),
        returned_on=returned_on,
    )
    if returned_on is None:
        await session.execute(
            text("UPDATE holdings SET status = 'on_loan' WHERE id = :id"), {"id": holding["id"]}
        )
    return loan
