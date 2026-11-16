"""공식 서지를 만드는 함수 하나. 서지정보 채움과 실험 장서 적재가 함께 부른다.

외부 값만 쓴다(`app/central/sources.py`의 `OfficialValues`). 이미 있는 공식 서지(같은 ISBN)는
고치지 않는다. 기여자와 시리즈 키를 함께 만든다. 공식 서지를 만드는 새 경로는 이 함수를 부른다.
"""

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.contributors import sync_contributors
from app.central.models import Book
from app.central.sources import OfficialValues
from app.core.text import match_key


def series_keys(names: tuple[str, ...] | list[str]) -> list[str]:
    """시리즈마다 이름 맞춤 키. 빈 키와 중복은 빼고 순서는 지킨다."""
    keys: list[str] = []
    for name in names:
        key = match_key(name)
        if key and key not in keys:
            keys.append(key)
    return keys


async def count_missing_series_keys(session: AsyncSession) -> int:
    """시리즈명이 있는데 시리즈 키가 빈 공식 서지 수.

    키는 응답의 시리즈 목록에서만 만들 수 있어 세기만 한다.
    """
    return await session.scalar(
        select(func.count())
        .select_from(Book)
        .where(func.coalesce(func.btrim(Book.series_name), "") != "", Book.series_keys == [])
    )


async def find_official(session: AsyncSession, isbn: str) -> Book | None:
    return await session.scalar(select(Book).where(Book.isbn == isbn))


async def create_official(session: AsyncSession, isbn: str, values: OfficialValues) -> Book:
    """ISBN의 공식 서지를 외부 값으로 만든다. 이미 있으면 그대로 돌려준다(고치지 않는다)."""
    await session.execute(
        insert(Book)
        .values(
            isbn=isbn,
            title=values.title,
            author=values.author,
            publisher=values.publisher,
            published_date=values.published_date,
            list_price=values.list_price,
            kdc=values.kdc,
            kdc_name=values.kdc_name,
            cover_url=values.cover_url,
            description=values.description,
            subtitle=values.subtitle,
            table_of_contents=values.table_of_contents,
            series_name=values.series_name,
            series_keys=series_keys(values.series_names),
            addition_symbol=values.addition_symbol,
            volume=values.volume,
            external_source=values.source,
            field_sources=values.field_sources,
            external_url=values.url,
            external_category=values.category,
        )
        .on_conflict_do_nothing(index_elements=["isbn"])
    )
    book = await find_official(session, isbn)
    assert book is not None
    await sync_contributors(session, book)
    return book
