"""공식 서지의 기여자. 저자 원문을 출처에 맞는 해석기로 풀어 `book_contributors`에 둔다.

기관 모델을 모른다. 공식 서지를 만드는 모든 경로(채움, 시드, 평가 표본 적재)가 `sync_contributors`를
부르고, 역할 표나 규칙을 고친 뒤에는 `scripts/rebuild_contributors.py`가 다시 맞춘다.
원문 `Book.author`는 바꾸지 않는다. 기여자는 원문에서 다시 만들 수 있는 파생 값이다.
"""

from collections.abc import Callable

from sqlalchemy import delete, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.external.yes24.contributors import parse_yes24_author
from app.central.models import Book, BookContributor, ExternalSource
from app.core.contributors import Contributor, parse_author_text

NAME_LIMIT = 200  # BookContributor.name, name_key 열 길이
ROLE_TEXT_LIMIT = 50

# 출처별 해석기. 출처가 없거나 표에 없으면 기관 파일 해석기(꼴이 정해지지 않은 원문)를 쓴다.
# 정보나루 원문(이름표 꼴·괄호 꼴)과 카카오 배열을 이은 원문은 기관 파일 해석기가 읽는 꼴이다.
PARSERS: dict[ExternalSource, Callable[[str], list[Contributor]]] = {
    ExternalSource.YES24: parse_yes24_author,
    ExternalSource.DATA4LIBRARY: parse_author_text,
    ExternalSource.KAKAO: parse_author_text,
}


def parse_book_author(book: Book) -> list[Contributor]:
    return PARSERS.get(book.external_source, parse_author_text)(book.author)


def _rows(book: Book) -> list[dict]:
    return [
        {
            "book_id": book.id,
            "position": position,
            "name": person.name[:NAME_LIMIT],
            "name_key": person.name_key[:NAME_LIMIT],
            "role": person.role,
            "role_text": person.role_text[:ROLE_TEXT_LIMIT] if person.role_text else None,
        }
        for position, person in enumerate(parse_book_author(book))
    ]


_FIELDS = ("position", "name", "name_key", "role", "role_text")


async def sync_contributors(session: AsyncSession, book: Book, *, write: bool = True) -> bool:
    """공식 서지의 기여자를 지금 규칙으로 맞춘다. 저장된 값과 같으면 쓰지 않는다.

    지금 규칙과 달랐으면 True다. write가 False면 비교만 하고 쓰지 않는다(확인 방식).
    """
    wanted = _rows(book)
    stored = (
        await session.execute(
            select(*(getattr(BookContributor, f) for f in _FIELDS))
            .where(BookContributor.book_id == book.id)
            .order_by(BookContributor.position)
        )
    ).all()
    if [tuple(row) for row in stored] == [tuple(r[f] for f in _FIELDS) for r in wanted]:
        return False
    if not write:
        return True
    await session.execute(delete(BookContributor).where(BookContributor.book_id == book.id))
    if wanted:
        await session.execute(insert(BookContributor), wanted)
    return True


REBUILD_BATCH = 500


async def rebuild_contributors(session: AsyncSession, *, write: bool = True) -> tuple[int, int]:
    """모든 공식 서지의 기여자를 지금 규칙으로 맞춘다. (지금 규칙과 달랐던 건수, 전체 건수).

    운영자 실행(`scripts/rebuild_contributors.py`)이다. 저자 원문은 바꾸지 않는다.
    커밋은 부르는 쪽이 한다.
    """
    changed = total = 0
    last_id = 0
    while True:
        books = (
            await session.scalars(
                select(Book).where(Book.id > last_id).order_by(Book.id).limit(REBUILD_BATCH)
            )
        ).all()
        if not books:
            return changed, total
        last_id = books[-1].id
        for book in books:
            total += 1
            changed += await sync_contributors(session, book, write=write)
