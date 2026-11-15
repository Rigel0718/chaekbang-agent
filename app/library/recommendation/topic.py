"""주제로 찾기: "공룡 책", "가벼운 에세이" 같은 요청의 후보 순위. LLM을 쓰지 않는다.

키워드 순위와 벡터 순위를 역순위 합(RRF)으로 합치고, 같은 시리즈를 묶고, MMR로 다양하게 한다.
범위(그 기관, 추천 가능, 부르는 쪽이 넘긴 조건)는 신호마다 순위를 매기기 전에 건다. 조건의 뜻
(예: 어린이 도서)은 여기서 모른다. 어린이 기능이 조건을 만들어 넘긴다.

설정(`TopicSettings`)은 추천 실험(`evals/recommendation`)이 정한다. REST와 tool에는 아직 잇지
않는다(`add-related-books`).
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Literal

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.embedding import Embedder
from app.central.models import Book
from app.core.embedding_text import TextKind
from app.library.models.catalog import LibraryBook
from app.library.recommendation.embeddings import book_vectors, similar_books
from app.library.recommendation.ranking import RRF_K, Ranked, cap_series, fuse_rrf, mmr
from app.library.recommendation.search import clean_keywords, ranked_query

KEYWORD = "keyword"
VECTOR = "vector"
TOPIC_LIMIT = 5
TOPIC_DEPTH = 30


@dataclass(frozen=True)
class TopicSettings:
    keyword_weight: float = 1.0  # 0이면 키워드 신호를 쓰지 않는다
    vector_weight: float = 1.0  # 0이면 벡터 신호를 쓰지 않는다(인코더를 부르지 않는다)
    vector_input: Literal["text", "keywords"] = "text"  # 벡터 질의: 이용자 문장 / 낱말을 이은 것
    weights: Mapping[TextKind, float] = field(default_factory=lambda: {TextKind.FULL: 1.0})
    depth: int = TOPIC_DEPTH  # 신호마다 가져올 순위 깊이
    rrf_k: int = RRF_K
    series_cap: int | None = None  # 같은 시리즈 상한. None이면 묶지 않는다
    mmr_lambda: float | None = None  # None이면 다양화하지 않는다
    limit: int = TOPIC_LIMIT


async def keyword_ranking(
    session: AsyncSession,
    library_id: int,
    keywords: Sequence[str],
    *,
    within: Select | None = None,
    depth: int = TOPIC_DEPTH,
) -> list[int]:
    """키워드 검색과 같은 점수·같은 순서로, 깊이까지의 기관 도서 id.

    키워드 검색의 결과 상한(10권)에 묶이지 않는다. 낱말이 없거나 하나도 맞지 않으면 비어 있다.
    """
    words = clean_keywords(keywords)
    if not words:
        return []
    rows = await session.execute(ranked_query(library_id, words, within).limit(depth))
    return [book.id for book, *_ in rows.unique()]


async def _series_keys(
    session: AsyncSession, library_id: int, ids: Sequence[int]
) -> dict[int, list[str]]:
    """공식 서지의 시리즈 키. 연결되지 않은 책은 시리즈가 없다."""
    rows = await session.execute(
        select(LibraryBook.id, Book.series_keys)
        .join(Book, Book.id == LibraryBook.book_id)
        .where(LibraryBook.library_id == library_id, LibraryBook.id.in_(list(ids)))
    )
    return {book_id: list(keys) for book_id, keys in rows if keys}


async def find_by_topic(
    session: AsyncSession,
    embedder: Embedder,
    *,
    library_id: int,
    text: str,
    keywords: Sequence[str],
    within: Select | None = None,
    settings: TopicSettings | None = None,
) -> list[Ranked]:
    """그 기관의 추천 가능한 책 중 조건 안의 책을 주제에 맞는 순서로.

    text는 이용자 문장, keywords는 사서가 넘긴 낱말이다. 결과마다 합친 점수와 신호별 순위(근거),
    시리즈 묶기로 빠진 권수가 있다. 같은 데이터·질의·설정이면 같은 결과다.
    """
    settings = settings or TopicSettings()
    rankings: dict[str, list[int]] = {}
    if settings.keyword_weight > 0:
        rankings[KEYWORD] = await keyword_ranking(
            session, library_id, keywords, within=within, depth=settings.depth
        )
    if settings.vector_weight > 0:
        joined = " ".join(word.strip() for word in keywords if word.strip())
        query = joined if settings.vector_input == "keywords" and joined else text
        found = await similar_books(
            session,
            embedder,
            library_id=library_id,
            query=query,
            limit=settings.depth,
            weights=settings.weights,
            within=within,
        )
        rankings[VECTOR] = [f.library_book.id for f in found]
    ranked = fuse_rrf(
        rankings,
        k=settings.rrf_k,
        weights={KEYWORD: settings.keyword_weight, VECTOR: settings.vector_weight},
    )
    ids = [item.library_book_id for item in ranked]
    if settings.series_cap is not None and ids:
        ranked = cap_series(
            ranked, await _series_keys(session, library_id, ids), settings.series_cap
        )
    if settings.mmr_lambda is not None and len(ranked) > 1:
        vectors = await book_vectors(
            session, embedder.name, library_id, [item.library_book_id for item in ranked]
        )
        ranked = mmr(ranked, vectors, settings.mmr_lambda)
    return ranked[: settings.limit]
