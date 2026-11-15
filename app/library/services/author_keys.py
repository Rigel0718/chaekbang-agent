"""기관 도서 저자 키 다시 맞추기와 분류기호 확인.

운영자 실행(`scripts/rebuild_contributors.py`)이 쓴다. 저자 키는 저장할 때 모델이 계산한다
(`LibraryBook._set_author_keys`). 역할 표나 이름 맞춤 규칙을 고치면 옛 규칙으로 저장된 행이
남으므로 이 함수로 다시 맞춘다. 파생 값만 쓰고 기관이 정한 값(서명, 저자 원문, 분류기호)은
바꾸지 않는다. 훅을 부르지 않는다.
"""

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contributors import author_keys
from app.core.text import kdc_key
from app.library.models.catalog import LibraryBook

REBUILD_BATCH = 1000


async def rebuild_author_keys(session: AsyncSession, *, write: bool = True) -> tuple[int, int]:
    """모든 기관의 기관 도서 저자 키를 지금 규칙으로 맞춘다. (달랐던 건수, 전체 건수).

    write가 False면 세기만 한다. 커밋은 부르는 쪽이 한다.
    """
    changed = total = 0
    last_id = 0
    while True:
        rows = (
            await session.execute(
                select(LibraryBook.id, LibraryBook.author, LibraryBook.author_keys)
                .where(LibraryBook.id > last_id)
                .order_by(LibraryBook.id)
                .limit(REBUILD_BATCH)
            )
        ).all()
        if not rows:
            return changed, total
        last_id = rows[-1].id
        for library_book_id, author, stored in rows:
            total += 1
            wanted = author_keys(author)
            if list(stored) == wanted:
                continue
            changed += 1
            if write:
                await session.execute(
                    update(LibraryBook)
                    .where(LibraryBook.id == library_book_id)
                    .values(author_keys=wanted)
                )


async def count_unnormalized_kdc(session: AsyncSession) -> int:
    """KDC로 읽을 수 있는데 맞춘 값과 다르게 저장된 분류기호 수.

    기관 값이라 고치지 않고 세기만 한다.
    """
    values = await session.scalars(select(LibraryBook.kdc).where(LibraryBook.kdc.is_not(None)))
    return sum(1 for value in values if (key := kdc_key(value)) is not None and key != value)
