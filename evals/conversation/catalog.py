"""실험 장서를 테스트 DB에 넣는다. 개발 DB의 실험 기관과 같은 적재 코드(`seed_experiment`)다.

- 부르는 쪽이 되돌릴 트랜잭션 안에서 부른다(`evals/librarian/__main__.py`의 `rollback_session`).
  개발 DB는 읽지도 쓰지도 않는다.
- 책 키(`isbn:`/`acc:`)는 적재 규칙에서 나오므로 개발 DB 실험 장서와 같아, 추천 실험의 라벨을 그대로
  쓴다.
- 인코더를 넘기면 벡터 두 층(종류 `full`)을 운영자 실행과 같은 적재 코드로 넣는다. 평가는 문서 벡터
  캐시(`DOC_VECTORS`)를 쓴 인코더를 넘겨, 처음 한 번만 임베딩 서버로 인코딩한다.
- 규칙 검사가 쓰는 장서 정보는 AI 사서 평가와 같은 모양(`SampleCatalog`)으로 DB에서 읽는다.
"""

from dataclasses import dataclass, field, replace
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.central.embedding import Embedder
from app.features.children.models import Audience, LibraryBookAudience
from app.library.models.catalog import Holding, LibraryBook
from app.library.models.library import Library, LoanMode
from app.library.recommendation.search import RECOMMENDABLE_STATUSES
from app.seed.experiment import LIBRARY_NAME, load_collection, load_sources, seed_experiment
from evals.collection.fetch import DATA_FILE as COLLECTION_FILE
from evals.collection.plan import FIELDS
from evals.collection.sources import SOURCES_FILE
from evals.librarian.catalog import BookState, SampleCatalog, load_vectors
from evals.recommendation.keys import library_keys

DATA_DIR = Path(__file__).parent / "data"
DOC_VECTORS = DATA_DIR / "doc_vectors.json"  # 실험 장서 문서 벡터 캐시
QUERY_VECTORS = DATA_DIR / "query_vectors.json"  # 평가 중 질의 벡터 캐시
EVAL_PASSWORD = "conversation-eval"  # 되돌릴 트랜잭션 안의 가상 계정. 함께 사라진다


@dataclass
class ExperimentCatalog(SampleCatalog):
    keys: dict[str, int] = field(default_factory=dict)  # 책 키 → 기관 도서 id

    @property
    def key_of(self) -> dict[int, str]:
        return {book_id: key for key, book_id in self.keys.items()}


def _text(book: LibraryBook) -> str:
    official = book.book
    parts = [
        book.shown("title"),
        official.subtitle if official is not None else None,
        official.series_name if official is not None else None,
        book.shown("author"),
        book.shown("description"),
    ]
    return "\n".join(p for p in parts if p)


async def read_catalog(session: AsyncSession, library_id: int) -> ExperimentCatalog:
    """그 기관의 책 키, 추천 가능, 어린이, 서명, 서지 글을 읽는다."""
    library = await session.get(Library, library_id)
    assert library is not None
    catalog = ExperimentCatalog(library_id, LoanMode(library.loan_mode))
    books = await session.scalars(
        select(LibraryBook)
        .where(LibraryBook.library_id == library_id)
        .options(selectinload(LibraryBook.book))
        .order_by(LibraryBook.id)
    )
    recommendable = set(
        await session.scalars(
            select(Holding.library_book_id).where(
                Holding.library_id == library_id, Holding.status.in_(RECOMMENDABLE_STATUSES)
            )
        )
    )
    for book in books:
        catalog.states[book.id] = (
            BookState.AVAILABLE if book.id in recommendable else BookState.LOST_ONLY
        )
        catalog.titles[book.id] = book.shown("title")
        catalog.texts[book.id] = _text(book)
        if book.book_id is not None:
            catalog.official.add(book.id)
    catalog.children = set(
        await session.scalars(
            select(LibraryBookAudience.library_book_id).where(
                LibraryBookAudience.library_id == library_id,
                LibraryBookAudience.audience == Audience.CHILDREN,
            )
        )
    )
    catalog.keys = await library_keys(session, library_id)
    return catalog


async def load_experiment(
    session: AsyncSession,
    *,
    collection_path: Path = COLLECTION_FILE,
    sources_path: Path = SOURCES_FILE,
    embedder: Embedder | None = None,
) -> ExperimentCatalog:
    """실험 장서를 넣고 장서 정보를 돌려준다. 파일이 없으면 `CollectionMissingError`다."""
    collection = load_collection(collection_path, {f.key: f.shelf for f in FIELDS})
    collection = replace(collection, sources=load_sources(sources_path))
    await seed_experiment(session, collection, EVAL_PASSWORD, EVAL_PASSWORD)
    await session.commit()
    library_id = await session.scalar(select(Library.id).where(Library.name == LIBRARY_NAME))
    assert library_id is not None
    catalog = await read_catalog(session, library_id)
    if embedder is not None:
        catalog.vectors = await load_vectors(session, embedder, library_id)
        await session.commit()
    return catalog
