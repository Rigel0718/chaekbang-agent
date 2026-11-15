"""책 키와 분야. 라벨·기준 책·최근 기록이 책을 가리키는 방법이다.

- 키: `isbn:<13자리>`, ISBN이 없으면 `acc:<그 책 사본 중 가장 앞선 등록번호>`.
  DB의 id는 실험 장서를 다시 넣으면 바뀌지만, ISBN과 등록번호(적재가 ISBN 순서로 붙인다)는 같다.
- 분야: DB에는 없고 실험 장서 파일에만 있다. 적재와 같은 순서 번호로 등록번호에 맞춘다.
"""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.external.yes24.parsing import parse_item
from app.core.isbn import normalize_isbn
from app.library.models.catalog import Holding, LibraryBook
from app.seed.experiment import ACCESSION_PREFIX, layout, load_collection
from evals.collection.plan import FIELDS

DATA_DIR = Path(__file__).parent / "data"
HOLDOUT_FIELDS = frozenset(field.key for field in FIELDS if field.holdout)
FIELD_KEYS = frozenset(field.key for field in FIELDS)
CHILDREN_FIELDS = ("toddler", "children")


def book_key(isbn: str | None, accession: str | None) -> str:
    if isbn:
        return f"isbn:{isbn}"
    if accession:
        return f"acc:{accession}"
    raise ValueError("ISBN도 등록번호도 없는 책은 가리킬 수 없습니다")


async def library_keys(session: AsyncSession, library_id: int) -> dict[str, int]:
    """그 기관의 책 키 → 기관 도서 id. 사본이 없는 ISBN 없는 책은 빠진다."""
    first = (
        select(Holding.library_book_id, func.min(Holding.accession_number).label("accession"))
        .where(Holding.library_id == library_id)
        .group_by(Holding.library_book_id)
        .subquery()
    )
    rows = await session.execute(
        select(LibraryBook.id, LibraryBook.isbn, first.c.accession)
        .outerjoin(first, first.c.library_book_id == LibraryBook.id)
        .where(LibraryBook.library_id == library_id)
    )
    return {
        book_key(isbn, accession): book_id for book_id, isbn, accession in rows if isbn or accession
    }


def fields_of(books: Sequence[Mapping[str, Any]]) -> dict[str, str]:
    """실험 장서 파일의 책 목록(`{"field", "item"}`) → 책 키별 분야.

    적재(`app/seed/experiment.py`)와 같은 규칙이다: ISBN 순서 번호 i로 ISBN 없는 책과 등록번호를
    정한다.
    """
    rows = sorted(
        ((normalize_isbn(parse_item(row["item"]).isbn13 or ""), row["field"]) for row in books),
        key=lambda pair: pair[0],
    )
    fields = {}
    for i, (isbn, field) in enumerate(rows):
        accession = f"{ACCESSION_PREFIX}{i + 1:05d}"
        fields[book_key(isbn if layout(i).with_isbn else None, accession)] = field
    return fields


def load_fields(path: Path) -> dict[str, str]:
    """실험 장서 파일에서 책 키별 분야를 읽는다. 파일이 없으면 `CollectionMissingError`다."""
    return fields_of(load_collection(path, {}).books)
