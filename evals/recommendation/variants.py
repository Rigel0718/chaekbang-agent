"""추천 실험의 변형. 세트(주제로 찾기, 비슷한 책, 최근 기록)마다 표가 따로 있다.

단계마다 앞 단계의 승자 위에 다음 단계를 얹는다(`add-recommendation-experiments` design 결정 7,
`add-related-book-experiments` design 결정 6·7).

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
from app.library.recommendation.related import (
    AUTHOR,
    CO_LOAN,
    KDC,
    LOAN_KINDS,
    MANIA,
    POPULAR_ALL,
    READER,
    SERIES,
    VECTOR,
    HistorySettings,
    LoanSignals,
    SimilarSettings,
    find_from_history,
    find_similar,
)
from app.library.recommendation.search import search_collection
from app.library.recommendation.topic import KEYWORD, TopicSettings, find_by_topic
from evals.recommendation.sets import TopicQuery

DEEP = 10  # 지표가 보는 깊이(Recall@10)

Runner = Callable[
    [AsyncSession, Embedder, int, TopicQuery, Select | None], Awaitable[Sequence[Ranked]]
]
Settings = TopicSettings | SimilarSettings | HistorySettings


@dataclass(frozen=True)
class Variant:
    name: str
    note: str
    settings: Settings | None = None  # 그 세트의 제품 함수에 넘길 설정
    runner: Runner | None = None  # 설정으로 나타낼 수 없는 것(지금 제품의 키워드 검색)


async def run_variant(
    session: AsyncSession,
    embedder: Embedder,
    variant: Variant,
    library_id: int,
    query,
    within: Select | None,
    loan_signals: LoanSignals | None = None,
    popular_group: str = POPULAR_ALL,
) -> Sequence[Ranked]:
    """변형 하나로 항목 하나의 상위 `DEEP`권. 어린이 조건(`within`)은 부르는 쪽이 넘긴다.

    항목은 주제 질의이거나, 기준 책들의 기관 도서 id(`base_ids`)를 가진 비슷한 책·최근 기록
    항목이다. 비슷한 책과 최근 기록은 저장된 벡터만 써서 인코더의 모델 이름만 쓴다.
    """
    if variant.runner is not None:
        return await variant.runner(session, embedder, library_id, query, within)
    assert variant.settings is not None
    if isinstance(variant.settings, SimilarSettings):
        return await find_similar(
            session,
            embedder.name,
            library_id=library_id,
            library_book_id=query.base_ids[0],
            within=within,
            settings=replace(variant.settings, limit=DEEP),
            loan_signals=loan_signals,
        )
    if isinstance(variant.settings, HistorySettings):
        return await find_from_history(
            session,
            embedder.name,
            library_id=library_id,
            library_book_ids=query.base_ids,
            within=within,
            settings=replace(variant.settings, limit=DEEP),
            loan_signals=loan_signals,
            popular_group=popular_group,
        )
    return await find_by_topic(
        session,
        embedder,
        library_id=library_id,
        text=query.text,
        keywords=query.keywords,
        within=within,
        settings=replace(variant.settings, limit=DEEP),
    )


def needs_loans(variant: Variant) -> bool:
    """정보나루 대출 신호(함께 대출·마니아·다독자)를 쓰는 변형인지."""
    settings = variant.settings
    if isinstance(settings, HistorySettings):
        if settings.method == "per-book":
            return needs_loans(Variant(variant.name, "", settings.similar))
        return settings.signals.get(CO_LOAN, 0) > 0
    if isinstance(settings, SimilarSettings):
        return any(settings.signals.get(kind, 0) > 0 for kind in LOAN_KINDS)
    return False


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

# --- 비슷한 책 (`add-related-book-experiments` design 결정 6, `add-loan-signals` 결정 6·10) ---
# 단계의 승자 (실행 결과를 보고 고친다)
BEST_SIM_KIND = "full"  # 단계 1: 벡터 이웃의 텍스트 종류
BEST_SIM_FUSION = "rrf"  # 단계 3: rrf / priority
BEST_SIM_RULE_WEIGHT = 1.0  # 단계 3: 규칙 신호(시리즈·저자·KDC) 가중치
BEST_SIM_SERIES_CAP: int | None = None  # 단계 4
BEST_SIM_MMR: float | None = None  # 단계 4
BEST_SIM_KDC_LEVEL = "section"  # 단계 5: section / three / nested
BEST_SIM_KDC_ORDER = "title"  # 단계 5: title / vector
BEST_SIM_KDC_WEIGHT = 1.0  # 단계 5: KDC 가중치(0이면 끔)
BEST_SIM_CO_LOAN = 0.0  # 단계 6: 함께 대출 가중치(0이면 끔)


def _sim_vector(kind: str = BEST_SIM_KIND, **changes) -> SimilarSettings:
    return replace(SimilarSettings(signals={VECTOR: 1.0}, weights=KINDS[kind]), **changes)


def _sim_fused(rule_weight: float = BEST_SIM_RULE_WEIGHT, **changes) -> SimilarSettings:
    base = SimilarSettings(
        signals={SERIES: rule_weight, AUTHOR: rule_weight, KDC: rule_weight, VECTOR: 1.0},
        fusion=BEST_SIM_FUSION,
        weights=KINDS[BEST_SIM_KIND],
    )
    return replace(base, **changes)


def _sim_signals(kdc: float = 1.0, **more: float) -> dict[str, float]:
    """규칙 신호(가중치 BEST_SIM_RULE_WEIGHT) + 벡터 1, KDC 가중치를 따로, 더 켤 신호."""
    rule = BEST_SIM_RULE_WEIGHT
    signals = {SERIES: rule, AUTHOR: rule, KDC: kdc * rule, VECTOR: 1.0, **more}
    return {name: weight for name, weight in signals.items() if weight > 0}


def _sim_kdc_best(**changes) -> SimilarSettings:
    """단계 5의 승자: 규칙 + 벡터에 KDC 단위·순서·가중치."""
    base = {
        "signals": _sim_signals(BEST_SIM_KDC_WEIGHT),
        "kdc_level": BEST_SIM_KDC_LEVEL,
        "kdc_order": BEST_SIM_KDC_ORDER,
    }
    return _sim_fused(**{**base, **changes})


def _sim_best(**changes) -> SimilarSettings:
    base = {
        "signals": _sim_signals(BEST_SIM_KDC_WEIGHT, **{CO_LOAN: BEST_SIM_CO_LOAN}),
        "series_cap": BEST_SIM_SERIES_CAP,
        "mmr_lambda": BEST_SIM_MMR,
    }
    return _sim_kdc_best(**{**base, **changes})


def _similar() -> list[Variant]:
    rules = {SERIES: 1.0, AUTHOR: 1.0, KDC: 1.0}
    no_kdc = {SERIES: BEST_SIM_RULE_WEIGHT, AUTHOR: BEST_SIM_RULE_WEIGHT, VECTOR: 1.0}
    with_loans = _sim_best().signals
    return [
        Variant("sim-vec", "0 기준: 벡터 이웃만, full", _sim_vector("full")),
        Variant("sim-vec-author", "1 벡터 이웃만, 저자 넣기", _sim_vector("author")),
        Variant("sim-vec-desc", "1 벡터 이웃만, 소개만", _sim_vector("desc")),
        Variant("sim-vec-fields", "1 벡터 이웃만, 필드별 1:1:1", _sim_vector("fields")),
        Variant(
            "sim-vec-cat",
            "1' 진단: 벡터 이웃을 같은 외부 분류 안으로",
            _sim_vector(category_scope=True),
        ),
        Variant(
            "sim-rules",
            "2 진단: 규칙만(시리즈 → 저자 → KDC), 벡터 없음",
            SimilarSettings(signals=rules, fusion="priority"),
        ),
        Variant("sim-rrf", "3 규칙 + 벡터 RRF 1:1", _sim_fused(1.0, fusion="rrf")),
        Variant("sim-rrf-rule2", "3 규칙 + 벡터 RRF, 규칙 가중치 2", _sim_fused(2.0, fusion="rrf")),
        Variant("sim-priority", "3 규칙 먼저, 그다음 벡터", _sim_fused(1.0, fusion="priority")),
        Variant(
            "sim-author-rrf",
            "3 규칙 + 벡터(저자 넣기) RRF 1:1",
            _sim_fused(1.0, fusion="rrf", weights=KINDS["author"]),
        ),
        Variant("sim-series1", "4 시리즈 상한 1", _sim_fused(series_cap=1)),
        Variant("sim-series2", "4 시리즈 상한 2", _sim_fused(series_cap=2)),
        Variant(
            "sim-mmr0.7", "4 MMR λ 0.7", _sim_fused(series_cap=BEST_SIM_SERIES_CAP, mmr_lambda=0.7)
        ),
        # 단계 5: KDC (`sim-rrf` 위에서 하나씩 바꾼다)
        Variant("sim-rrf-kdc0", "5 KDC의 몫: `sim-rrf`에서 KDC를 뺌", _sim_fused(signals=no_kdc)),
        Variant("sim-kdc", "5 진단: KDC 신호만, 벡터 없음", SimilarSettings(signals={KDC: 1.0})),
        Variant("sim-rrf-kdc3", "5 KDC 단위 세 자리", _sim_fused(kdc_level="three")),
        Variant(
            "sim-rrf-kdcn", "5 KDC 단위 계층(세목 먼저, 세 자리)", _sim_fused(kdc_level="nested")
        ),
        Variant("sim-rrf-kdcv", "5 KDC 세목 안 벡터 순서", _sim_fused(kdc_order="vector")),
        Variant("sim-rrf-kdc-w0.5", "5 KDC 가중치 0.5", _sim_fused(signals=_sim_signals(0.5))),
        Variant("sim-rrf-kdc-w2", "5 KDC 가중치 2", _sim_fused(signals=_sim_signals(2.0))),
        Variant(
            "sim-vec-kdc",
            "5 진단: 벡터 이웃을 같은 KDC 세목 안으로",
            _sim_vector(kdc_scope=True),
        ),
        Variant("sim-kdc-best", "5 확인: KDC 단계의 승자를 합친 설정", _sim_kdc_best()),
        # 단계 6: 함께 대출 (단계 5 승자 위에)
        Variant(
            "sim-best-co",
            "6 단계 5 승자 + 함께 대출 1:1",
            _sim_kdc_best(signals={**_sim_signals(BEST_SIM_KDC_WEIGHT), CO_LOAN: 1.0}),
        ),
        Variant("sim-co", "6 진단: 함께 대출만", SimilarSettings(signals={CO_LOAN: 1.0})),
        Variant(
            "sim-best-mania",
            "6 진단: 단계 5 승자 + 마니아 추천 1:1",
            _sim_kdc_best(signals={**_sim_signals(BEST_SIM_KDC_WEIGHT), MANIA: 1.0}),
        ),
        Variant(
            "sim-best-reader",
            "6 진단: 단계 5 승자 + 다독자 추천 1:1",
            _sim_kdc_best(signals={**_sim_signals(BEST_SIM_KDC_WEIGHT), READER: 1.0}),
        ),
        Variant("sim-best", "채택한 설정", _sim_best(signals=with_loans)),
        Variant(
            "sim-best-kdc0",
            "확인: 채택한 설정에서 KDC 신호를 뺌",
            _sim_best(signals={k: v for k, v in with_loans.items() if k != KDC}),
        ),
    ]


SIMILAR_VARIANTS: dict[str, Variant] = {variant.name: variant for variant in _similar()}
DEFAULT_SIMILAR = ("sim-vec", "sim-rrf", "sim-best")

# --- 최근 기록 (`add-related-book-experiments` design 결정 7, `add-loan-signals` 결정 9) ---
# 단계 1: mean / per-book. 2026-11-16: 벡터 평균. 책별 RRF는 k 60이면 크게 낮고 k 1이면 차이 없음
BEST_HIST_METHOD = "mean"
BEST_HIST_SERIES_CAP: int | None = None  # 단계 2
BEST_HIST_MMR: float | None = None  # 단계 2
BEST_HIST_SIGNALS: dict[str, float] = {VECTOR: 1.0}  # 단계 3: 벡터 평균과 합칠 기록 신호


def _hist(**changes) -> HistorySettings:
    base = HistorySettings(
        method=BEST_HIST_METHOD,
        similar=_sim_best(),
        weights=KINDS[BEST_SIM_KIND],
        kdc_level=BEST_SIM_KDC_LEVEL,
    )
    return replace(base, **changes)


def _history() -> list[Variant]:
    return [
        Variant("hist-mean", "0 기준: 기록 책 벡터 평균의 이웃", _hist(method="mean")),
        Variant("hist-per-book", "1 책별 비슷한 책 순위(채택 설정) RRF", _hist(method="per-book")),
        Variant(
            "hist-per-book-vec",
            "1' 책별 벡터 이웃만 RRF",
            _hist(method="per-book", similar=_sim_vector()),
        ),
        Variant(
            "hist-per-book-k1",
            "1'' 진단(결과를 본 뒤 더함): 책별 RRF의 k를 1로(각 책의 앞 순위를 크게)",
            _hist(method="per-book", rrf_k=1),
        ),
        Variant("hist-series1", "2 시리즈 상한 1", _hist(series_cap=1)),
        Variant(
            "hist-mmr0.7", "2 MMR λ 0.7", _hist(series_cap=BEST_HIST_SERIES_CAP, mmr_lambda=0.7)
        ),
        Variant(
            "hist-mean-rules",
            "3 벡터 평균 + 기록 책들의 KDC·겹치는 저자 RRF",
            _hist(method="mean", signals={VECTOR: 1.0, KDC: 1.0, AUTHOR: 1.0}),
        ),
        Variant(
            "hist-mean-co",
            "3 벡터 평균 + 기록 책들의 함께 대출 RRF",
            _hist(method="mean", signals={VECTOR: 1.0, CO_LOAN: 1.0}),
        ),
        Variant(
            "hist-mean-all",
            "3 벡터 평균 + KDC·겹치는 저자·함께 대출 RRF",
            _hist(method="mean", signals={VECTOR: 1.0, KDC: 1.0, AUTHOR: 1.0, CO_LOAN: 1.0}),
        ),
        Variant(
            "hist-best",
            "채택한 설정",
            _hist(
                series_cap=BEST_HIST_SERIES_CAP,
                mmr_lambda=BEST_HIST_MMR,
                signals=dict(BEST_HIST_SIGNALS),
            ),
        ),
    ]


HISTORY_VARIANTS: dict[str, Variant] = {variant.name: variant for variant in _history()}
DEFAULT_HISTORY = ("hist-mean", "hist-per-book", "hist-best")

# 남겨 둔 분야 세트에서 돌리는 변형(`add-loan-signals` design 결정 11). 결과를 본 뒤 더하지 않는다
HOLDOUT_VARIANTS: dict[str, tuple[str, ...]] = {
    "topic": ("current", "hybrid-k60"),
    "similar": ("sim-vec", "sim-rrf", "sim-best"),
    "history": ("hist-mean", "hist-best"),
}

VARIANT_SETS: dict[str, dict[str, Variant]] = {
    "topic": VARIANTS,
    "similar": SIMILAR_VARIANTS,
    "history": HISTORY_VARIANTS,
}
DEFAULT_SETS: dict[str, tuple[str, ...]] = {
    "topic": DEFAULT_VARIANTS,
    "similar": DEFAULT_SIMILAR,
    "history": DEFAULT_HISTORY,
}
