"""같은 지은이의 책. 추천의 "같은 저자" 신호를 저장 구조 수준에서 고정한다.

책의 지은이 키는 두 층에서 읽는다.
- 공식 서지에 연결된 책: 공식 서지 기여자(`book_contributors`) 중 `author`·`original`의 이름 맞춤 키
- 연결되지 않은 책: 기관 도서 저자 키(`library_books.author_keys`)

연결된 책은 기관이 적은 저자를 보지 않는다(표시 값과 같은 원칙). 그린이는 기본에 넣지 않는다.
점수와 다른 신호와 합치기는 추천 실험(`add-recommendation-experiments`)의 일이고, REST와 tool에는
아직 잇지 않는다(`add-related-books`).
"""

from sqlalchemy import ColumnElement, Select, Text, case, func, literal, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.models import Book, BookContributor
from app.core.contributors import WRITER_ROLES
from app.core.tenancy import get_owned
from app.core.text import korean_order
from app.library.models.catalog import LibraryBook
from app.library.recommendation.search import LABEL, recommendable_ids

SAME_AUTHOR_LIMIT = 20


def writer_keys_sql() -> ColumnElement:
    """기관 도서 행의 지은이 키 배열(SQL 식). 연결된 책은 기여자, 아니면 저자 키."""
    official = func.array(
        select(BookContributor.name_key)
        .where(
            BookContributor.book_id == LibraryBook.book_id,
            BookContributor.role.in_(WRITER_ROLES),
        )
        .order_by(BookContributor.position)
        .scalar_subquery()
    )
    return case((LibraryBook.book_id.is_not(None), official), else_=LibraryBook.author_keys)


async def same_author_books(
    session: AsyncSession,
    library_id: int,
    library_book_id: int,
    *,
    limit: int = SAME_AUTHOR_LIMIT,
    within: Select | None = None,
) -> list[LibraryBook]:
    """기준 책과 지은이가 한 명 이상 겹치는, 그 기관의 추천 가능한 다른 책.

    겹치는 지은이 수, 표시 서명의 서명 정렬 순서(가나다), id 순서다.
    다른 기관의 기준 책은 NotFoundError다. within은 순위 전에 거는 기관 도서 id 조건이다.
    """
    await get_owned(session, LibraryBook, library_id, library_book_id, label=LABEL)
    keys = writer_keys_sql().label("keys")
    base_keys = await session.scalar(select(keys).where(LibraryBook.id == library_book_id))
    if not base_keys:
        return []
    rows = (
        await session.execute(
            select(LibraryBook, keys)
            .outerjoin(Book, Book.id == LibraryBook.book_id)
            .where(
                LibraryBook.library_id == library_id,
                LibraryBook.id != library_book_id,
                LibraryBook.id.in_(recommendable_ids(library_id)),
                writer_keys_sql().op("&&")(literal(list(base_keys), ARRAY(Text))),
                *([LibraryBook.id.in_(within)] if within is not None else []),
            )
            # 서명 순서는 DB의 서명 정렬 순서(가나다)로 정하고, 아래에서는 겹치는 수로만 줄 세운다.
            .order_by(korean_order(func.coalesce(Book.title, LibraryBook.title)), LibraryBook.id)
        )
    ).all()
    wanted = set(base_keys)
    ranked = sorted(rows, key=lambda row: -len(wanted & set(row[1])))  # 안정 정렬
    return [book for book, _ in ranked[:limit]]
