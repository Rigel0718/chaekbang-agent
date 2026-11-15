"""공식 서지를 만드는 함수 하나. 서지정보 채움과 실험 장서 적재가 함께 부른다.

외부 응답 값만 쓴다. 이미 있는 공식 서지(같은 ISBN)는 고치지 않는다. 기여자와 시리즈 키를 함께
만든다. 공식 서지를 만드는 새 경로는 이 함수를 부른다.
"""

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.contributors import sync_contributors
from app.central.external.yes24.parsing import Yes24Item
from app.central.models import Book, ExternalSource
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


async def create_official(session: AsyncSession, isbn: str, item: Yes24Item) -> Book:
    """ISBN의 공식 서지를 외부 값으로 만든다. 이미 있으면 그대로 돌려준다(고치지 않는다)."""
    await session.execute(
        insert(Book)
        .values(
            isbn=isbn,
            title=item.title,
            author=item.author,
            publisher=item.publisher,
            published_date=item.published_date,
            list_price=item.list_price,
            cover_url=item.cover_url,
            description=item.description,
            subtitle=item.subtitle,
            table_of_contents=item.table_of_contents,
            series_name=item.series_name,
            series_keys=series_keys(item.series_names),
            external_source=ExternalSource.YES24,
            external_url=item.url,
            external_category=item.category,
        )
        .on_conflict_do_nothing(index_elements=["isbn"])
    )
    book = await find_official(session, isbn)
    assert book is not None
    await sync_contributors(session, book)
    return book
