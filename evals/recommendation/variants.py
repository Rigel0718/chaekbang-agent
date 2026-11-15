"""주제로 찾기의 변형. 단계마다 앞 단계의 승자 위에 다음 단계를 얹는다(design 결정 7).

단계의 승자는 실행 결과를 보고 사람이 정해 아래 `BEST_*`에 적는다. 근거는 change의 design과
README의 결과 표에 남긴다. 격자는 일부러 작게 둔다. 질의가 20개라 촘촘히 고르면 조정 세트에
맞춰질 뿐이다.
"""

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, replace

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.embedding import Embedder
from app.core.embedding_text import TextKind
from app.library.recommendation.ranking import Ranked
from app.library.recommendation.search import search_collection
from app.library.recommendation.topic import KEYWORD, TopicSettings, find_by_topic
from evals.recommendation.sets import TopicQuery

DEEP = 10  # 지표가 보는 깊이(Recall@10)

Runner = Callable[
    [AsyncSession, Embedder, int, TopicQuery, Select | None], Awaitable[Sequence[Ranked]]
]


@dataclass(frozen=True)
class Variant:
    name: str
    note: str
    settings: TopicSettings | None = None  # 주제로 찾기의 설정
    runner: Runner | None = None  # 설정으로 나타낼 수 없는 것(지금 제품의 키워드 검색)


async def run_variant(
    session: AsyncSession,
    embedder: Embedder,
    variant: Variant,
    library_id: int,
    query: TopicQuery,
    within: Select | None,
) -> Sequence[Ranked]:
    """변형 하나로 질의 하나의 상위 `DEEP`권. 어린이 조건(`within`)은 부르는 쪽이 넘긴다."""
    if variant.runner is not None:
        return await variant.runner(session, embedder, library_id, query, within)
    assert variant.settings is not None
    return await find_by_topic(
        session,
        embedder,
        library_id=library_id,
        text=query.text,
        keywords=query.keywords,
        within=within,
        settings=replace(variant.settings, limit=DEEP),
    )


def _current(split_text: bool) -> Runner:
    async def run(session, embedder, library_id, query, within) -> Sequence[Ranked]:
        keywords = query.text.split() if split_text else query.keywords
        found = await search_collection(session, library_id, keywords, within=within, limit=DEEP)
        return [
            Ranked(c.library_book.id, 1 / position, {KEYWORD: position})
            for position, c in enumerate(found, start=1)
        ]

    return run


FIELDS_EQUAL = {TextKind.TITLE: 1.0, TextKind.CATEGORY: 1.0, TextKind.DESCRIPTION: 1.0}
FIELDS_DESC2 = {TextKind.TITLE: 1.0, TextKind.CATEGORY: 1.0, TextKind.DESCRIPTION: 2.0}
KINDS: Mapping[str, Mapping[TextKind, float]] = {
    "full": {TextKind.FULL: 1.0},
    "author": {TextKind.WITH_AUTHOR: 1.0},
    "desc": {TextKind.DESCRIPTION: 1.0},
    "fields": FIELDS_EQUAL,
    "fields-desc2": FIELDS_DESC2,
}

# --- 단계의 승자 (실행 결과를 보고 고친다) ---
BEST_INPUT = "text"  # 단계 1: 벡터 질의 입력
BEST_KIND = "full"  # 단계 2·3': 텍스트 종류
BEST_RRF_K = 60  # 단계 3
BEST_KEYWORD_WEIGHT = 1.0  # 단계 3
BEST_SERIES_CAP: int | None = None  # 단계 4
BEST_MMR: float | None = None  # 단계 5


def _vector(kind: str, vector_input: str = BEST_INPUT) -> TopicSettings:
    return TopicSettings(keyword_weight=0, vector_input=vector_input, weights=KINDS[kind])


def _hybrid(**changes) -> TopicSettings:
    base = TopicSettings(
        vector_input=BEST_INPUT,
        weights=KINDS[BEST_KIND],
        rrf_k=BEST_RRF_K,
        keyword_weight=BEST_KEYWORD_WEIGHT,
    )
    return replace(base, **changes)


def _all() -> list[Variant]:
    return [
        Variant("current", "0 기준: 지금 제품의 키워드 검색(낱말)", runner=_current(False)),
        Variant(
            "current-split", "0 기준: 키워드 검색에 문장을 띄어쓰기로 나눠", runner=_current(True)
        ),
        Variant("vec-text", "1 벡터만, full, 질의는 문장", _vector("full", "text")),
        Variant("vec-kw", "1 벡터만, full, 질의는 낱말", _vector("full", "keywords")),
        Variant("vec-author", "2 벡터만, 저자 넣기", _vector("author")),
        Variant("vec-desc", "2 벡터만, 소개만", _vector("desc")),
        Variant("vec-fields", "2 벡터만, 필드별 1:1:1", _vector("fields")),
        Variant("vec-fields-desc2", "2 벡터만, 필드별 1:1:2", _vector("fields-desc2")),
        Variant("hybrid-k60", "3 키워드+벡터 RRF, k 60", _hybrid(rrf_k=60, keyword_weight=1.0)),
        Variant("hybrid-k10", "3 키워드+벡터 RRF, k 10", _hybrid(rrf_k=10, keyword_weight=1.0)),
        Variant("hybrid-kw0.5", "3 키워드 가중치 0.5", _hybrid(rrf_k=60, keyword_weight=0.5)),
        Variant("hybrid-kw2", "3 키워드 가중치 2", _hybrid(rrf_k=60, keyword_weight=2.0)),
        Variant("hybrid-full", "3' 합친 순위에서 full", _hybrid(weights=KINDS["full"])),
        Variant("hybrid-author", "3' 합친 순위에서 저자 넣기", _hybrid(weights=KINDS["author"])),
        Variant("hybrid-desc", "3' 합친 순위에서 소개만", _hybrid(weights=KINDS["desc"])),
        Variant("hybrid-fields", "3' 합친 순위에서 필드별 1:1:1", _hybrid(weights=FIELDS_EQUAL)),
        Variant(
            "hybrid-fields-desc2", "3' 합친 순위에서 필드별 1:1:2", _hybrid(weights=FIELDS_DESC2)
        ),
        Variant("hybrid", "3의 승자 설정", _hybrid()),
        Variant("series1", "4 시리즈 상한 1", _hybrid(series_cap=1)),
        Variant("series2", "4 시리즈 상한 2", _hybrid(series_cap=2)),
        Variant("mmr0.7", "5 MMR λ 0.7", _hybrid(series_cap=BEST_SERIES_CAP, mmr_lambda=0.7)),
        Variant("mmr0.5", "5 MMR λ 0.5", _hybrid(series_cap=BEST_SERIES_CAP, mmr_lambda=0.5)),
        Variant("best", "채택한 설정", _hybrid(series_cap=BEST_SERIES_CAP, mmr_lambda=BEST_MMR)),
    ]


VARIANTS: dict[str, Variant] = {variant.name: variant for variant in _all()}
DEFAULT_VARIANTS = ("current", "vec-text", "hybrid", "best")
