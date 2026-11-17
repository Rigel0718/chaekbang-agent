"""YES24 표본을 테스트 DB의 가상 기관에 넣는다. 평가와 표본 테스트가 같은 적재 코드를 쓴다.

개발 DB에 넣지 않는다. 부르는 쪽이 되돌릴 트랜잭션 안에서 부른다. 개발 DB에 넣는 실험 장서는
따로다(`app/seed/experiment.py`, `scripts/seed_experiment.py`).

- 서지는 표본의 실제 값이다. ISBN이 978·979로 시작하는 올바른 ISBN-13이면 공식 서지를 만들어 잇고,
  그 밖(상품 바코드 880, 잡지 ISSN 977)은 ISBN 없는 기관 도서로 넣는다. 작은도서관도 잡지와 토이북을
  ISBN 없이 등록하는 경우가 많다.
- 어린이 구분은 등록과 같은 경로(`apply_category`)로 실제 분류 값에서 정한다.
- 공식 서지의 기여자는 채움과 같은 경로(`sync_contributors`)로 만든다. 저자 키는 모델이 정한다.
- 사본 상태는 기관이 가상이라 ISBN 순서에 고정한 규칙으로 만든다. 표본을 다시 받으면 책이 바뀐다.
- 인코더를 넘기면 벡터 두 층(공식 서지 벡터, 기관 도서 벡터, 종류 `full`)을 운영자 실행과 같은 적재
  코드로 같은 트랜잭션에 넣는다. 평가는 문서 벡터 캐시(`DOC_VECTORS`)를 쓴 인코더를 넘겨, 처음
  한 번만 임베딩 서버로 인코딩한다.
"""

import json
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.contributors import sync_contributors
from app.central.embedding import Embedder
from app.central.models import Book, ExternalSource
from app.central.official_embeddings import run_official_embedding
from app.core.isbn import InvalidIsbnError, normalize_isbn
from app.features.children.models import Audience, LibraryBookAudience
from app.features.children.service import apply_category
from app.library.models.catalog import (
    AcquisitionType,
    EnrichmentStatus,
    Holding,
    HoldingStatus,
    LibraryBook,
)
from app.library.models.library import Library, LibraryType, LoanMode
from app.library.recommendation.embeddings import run_library_embedding

DATA_FILE = Path(__file__).parent / "data" / "yes24_sample.json"
DOC_VECTORS = DATA_FILE.parent / "doc_vectors.json"  # 표본 문서 벡터 캐시
QUERY_VECTORS = DATA_FILE.parent / "query_vectors.json"  # 평가 중 질의 벡터 캐시
LIBRARY_NAME = "평가용 가상 작은도서관"


class SampleMissingError(FileNotFoundError):
    pass


class BookState(StrEnum):
    AVAILABLE = "available"  # 대출 가능 사본이 있다
    ON_LOAN = "on_loan"  # 사본이 모두 대출 중
    LOST_ONLY = "lost_only"  # 분실 사본만 있다. 추천하면 안 된다
    NO_DESCRIPTION = "no_description"  # 소개를 지웠다. 대출 가능
    NO_ISBN = "no_isbn"  # ISBN과 공식 서지 없이 넣었다. 대출 가능


# ISBN 순서의 나머지로 상태를 정한다. 나머지가 표에 없으면 대출 가능이다.
STATE_RULES = {
    3: BookState.NO_ISBN,
    5: BookState.NO_DESCRIPTION,
    7: BookState.LOST_ONLY,
    8: BookState.ON_LOAN,
}
STATE_MODULO = 10


@dataclass(frozen=True)
class Sample:
    fetched_on: str
    books: list[dict[str, Any]]


@dataclass
class SampleCatalog:
    library_id: int
    loan_mode: LoanMode
    states: dict[int, BookState] = field(default_factory=dict)  # 기관 도서 id → 상태
    titles: dict[int, str] = field(default_factory=dict)
    texts: dict[int, str] = field(default_factory=dict)  # 서명·부제·시리즈·저자·소개를 이은 글
    children: set[int] = field(default_factory=set)
    official: set[int] = field(default_factory=set)  # 공식 서지에 이은 책
    barcode_only: set[int] = field(default_factory=set)  # 표본의 ISBN이 ISBN이 아닌 책
    shelved: int | None = None  # 서가 위치를 따로 둔 책(안내 평가의 책 위치 시나리오)
    vectors: int = 0  # 적재한 벡터 수(두 층 합)

    @property
    def recommendable(self) -> set[int]:
        return {i for i, s in self.states.items() if s != BookState.LOST_ONLY}

    def with_state(self, state: BookState) -> list[int]:
        return sorted(i for i, s in self.states.items() if s == state)

    @property
    def children_pick(self) -> int:
        """관련 책 시나리오에서 고를 어린이 도서: 추천 가능한 어린이 도서 중 id가 가장 작은 책."""
        return min(self.children & self.recommendable)


def load_sample(path: Path = DATA_FILE) -> Sample:
    if not path.exists():
        raise SampleMissingError(f"표본이 없습니다: {path}")
    document = json.loads(path.read_text(encoding="utf-8"))
    return Sample(document["fetched_on"], document["books"])


def real_isbn(value: str | None) -> str | None:
    """978·979로 시작하는 올바른 ISBN-13만 ISBN으로 본다."""
    if not value or not value.startswith(("978", "979")):
        return None
    try:
        return normalize_isbn(value)
    except InvalidIsbnError:
        return None


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _text(row: dict[str, Any], description: str | None) -> str:
    parts = [row.get(k) for k in ("title", "subtitle", "series_name", "author")] + [description]
    return "\n".join(p for p in parts if p)


async def load_catalog(
    session: AsyncSession,
    sample: Sample,
    *,
    loan_mode: LoanMode = LoanMode.INTERNAL,
    embedder: Embedder | None = None,
) -> SampleCatalog:
    """가상 기관을 만들고 표본을 넣는다. 커밋은 부르는 쪽의 savepoint 안에서 일어난다.

    인코더가 있으면 표본의 두 층 벡터도 넣는다. 인코딩이 멈추면 `EmbeddingError`를 그대로 올린다.
    """
    library = Library(
        name=f"{LIBRARY_NAME} ({loan_mode.value})",
        type=LibraryType.SMALL_LIBRARY,
        loan_mode=loan_mode,
        default_loan_days=14,
    )
    session.add(library)
    await session.flush()
    catalog = SampleCatalog(library.id, loan_mode)
    rows = sorted(sample.books, key=lambda r: r["isbn13"])
    for index, row in enumerate(rows):
        state = STATE_RULES.get(index % STATE_MODULO, BookState.AVAILABLE)
        isbn = real_isbn(row["isbn13"])
        if isbn is None:
            state = BookState.AVAILABLE if state == BookState.NO_ISBN else state
        if state == BookState.NO_ISBN:
            isbn = None
        description = None if state == BookState.NO_DESCRIPTION else row.get("description")
        book = None
        if isbn is not None:
            book = Book(
                isbn=isbn,
                title=row["title"],
                author=row["author"],
                publisher=row.get("publisher"),
                published_date=_date(row.get("published_date")),
                description=description,
                table_of_contents=row.get("table_of_contents"),
                cover_url=row.get("cover_url"),
                subtitle=row.get("subtitle"),
                series_name=row.get("series_name"),
                external_source=ExternalSource.YES24,
                external_url=row.get("url"),
                external_category=row.get("category"),
            )
            session.add(book)
        library_book = LibraryBook(
            library_id=library.id,
            isbn=isbn,
            title=row["title"],
            author=row["author"],
            publisher=row.get("publisher"),
            description=description if book is None else None,
            book=book,
            enrichment_status=EnrichmentStatus.ENRICHED if book else EnrichmentStatus.PENDING,
        )
        session.add(library_book)
        await session.flush()
        if book is not None:
            await sync_contributors(session, book)  # 공식 서지를 만드는 다른 경로와 같다
        status = {
            BookState.LOST_ONLY: HoldingStatus.LOST,
            BookState.ON_LOAN: HoldingStatus.ON_LOAN,
        }.get(state, HoldingStatus.AVAILABLE)
        session.add(
            Holding(
                library_id=library.id,
                library_book_id=library_book.id,
                accession_number=f"EV{index + 1:05d}",
                shelf_location="평가 서가",
                status=status,
                acquisition_type=AcquisitionType.DONATED,
            )
        )
        await apply_category(session, library_book)
        catalog.states[library_book.id] = state
        catalog.titles[library_book.id] = row["title"]
        catalog.texts[library_book.id] = _text(row, description)
        if book is not None:
            catalog.official.add(library_book.id)
        if real_isbn(row["isbn13"]) is None:
            catalog.barcode_only.add(library_book.id)
    await session.flush()
    stored = await session.scalars(
        select(LibraryBookAudience.library_book_id).where(
            LibraryBookAudience.library_id == library.id,
            LibraryBookAudience.audience == Audience.CHILDREN,
        )
    )
    catalog.children = set(stored)
    await session.commit()
    if embedder is not None:
        catalog.vectors = await load_vectors(session, embedder, library.id)
    return catalog


async def load_vectors(session: AsyncSession, embedder: Embedder, library_id: int) -> int:
    official = select(LibraryBook.book_id).where(
        LibraryBook.library_id == library_id, LibraryBook.book_id.is_not(None)
    )
    total = 0
    for run in (
        await run_official_embedding(session, embedder, full=True, within=official),
        await run_library_embedding(session, embedder, full=True, library_id=library_id),
    ):
        if run.stopped is not None:
            raise run.stopped
        total += run.encoded
    return total
