"""비슷한 책과 최근 기록 추천: 기준 책(들)에서 후보 순위를 만든다. LLM을 쓰지 않는다.

신호는 같은 시리즈, 같은 저자, 같은 KDC 세목, 벡터 이웃(기준 책의 저장된 벡터)이다. 신호별 순위를
역순위 합(RRF)으로 합치거나 규칙 신호를 먼저 둔다. 결과마다 신호별 순위(근거)가 있다.

범위(그 기관, 추천 가능, 부르는 쪽이 넘긴 조건)는 신호마다 순위를 매기기 전에 건다. 조건의 뜻
(예: 어린이 도서)은 여기서 모른다. 기준 책 자신과 같은 책의 다른 판본은 결과에 내지 않는다.

설정은 추천 실험(`evals/recommendation`)이 정한다. REST와 tool에는 아직 잇지 않는다
(`add-related-books`).
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import timedelta
from typing import Literal, Protocol

from sqlalchemy import Select, Text, func, literal, select
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.models import Book
from app.core import clock
from app.core.embedding_text import TextKind
from app.core.tenancy import get_owned
from app.core.text import kdc_key, korean_order, match_key, strip_edition
from app.library.models.catalog import Holding, LibraryBook
from app.library.models.circulation import Loan
from app.library.recommendation.authors import same_author_books, writer_keys_sql
from app.library.recommendation.embeddings import book_vectors, neighbors_of
from app.library.recommendation.ranking import RRF_K, Ranked, cap_series, fuse_rrf, mmr
from app.library.recommendation.search import LABEL, recommendable_ids

SERIES = "series"
AUTHOR = "author"
KDC = "kdc"
CATEGORY = "category"
VECTOR = "vector"
CO_LOAN = "co_loan"  # 함께 대출된 책(정보나루, 전국)
MANIA = "mania"  # 진단: 정보나루 마니아 추천
READER = "reader"  # 진단: 정보나루 다독자 추천
LOAN_KINDS = (CO_LOAN, MANIA, READER)
POPULAR = "popular"  # 우리 도서관 인기(근거 이름)
NATIONAL_POPULAR = "national_popular"  # 정보나루 인기(근거 이름)
POPULAR_ALL = "all"  # 정보나루 인기의 연령 묶음: 조건 없음. 다른 묶음 이름은 부르는 쪽이 정한다
RULE_SIGNALS = (SERIES, AUTHOR, KDC)
RELATED_LIMIT = 5
RELATED_DEPTH = 30
POPULAR_DAYS = 180
BOOK_SIGNAL = "book:"  # 최근 기록의 근거 이름: `book:<기록 책의 기관 도서 id>`

_KDC_SECTION = r"^\d{3}(?:\.\d)?"  # 세목: 소수점 첫째 자리까지(없으면 세 자리)
_KDC_THREE = r"^\d{3}"  # 앞 세 자리
KdcLevel = Literal["section", "three", "nested"]
KdcOrder = Literal["title", "vector"]
_ISBN_SHOWN = func.coalesce(Book.isbn, LibraryBook.isbn)  # 공식 서지 ISBN이 먼저
_TITLE = func.coalesce(Book.title, LibraryBook.title)  # 표시 서명
_KDC_SHOWN = func.coalesce(Book.kdc, LibraryBook.kdc)  # 표시 KDC


def kdc_section(value: str | None) -> str | None:
    """KDC 세목 키. `813.72` → `813.7`, `813` → `813`. KDC가 아니면 None이다."""
    key = kdc_key(value)
    match = re.match(_KDC_SECTION, key) if key else None
    return match.group() if match else None


def _scope(library_id: int, within: Select | None, exclude: Sequence[int]) -> list:
    conditions = [
        LibraryBook.library_id == library_id,
        LibraryBook.id.in_(recommendable_ids(library_id)),
    ]
    if within is not None:
        conditions.append(LibraryBook.id.in_(within))
    if exclude:
        conditions.append(LibraryBook.id.not_in(list(exclude)))
    return conditions


async def _in_title_order(
    session: AsyncSession, library_id: int, within: Select | None, base_id: int, depth: int, *where
) -> list[int]:
    rows = await session.scalars(
        select(LibraryBook.id)
        .outerjoin(Book, Book.id == LibraryBook.book_id)
        .where(*_scope(library_id, within, [base_id]), *where)
        .order_by(korean_order(_TITLE), LibraryBook.id)
        .limit(depth)
    )
    return list(rows)


async def _base_value(session: AsyncSession, library_id: int, library_book_id: int, column):
    await get_owned(session, LibraryBook, library_id, library_book_id, label=LABEL)
    return await session.scalar(
        select(column)
        .select_from(LibraryBook)
        .outerjoin(Book, Book.id == LibraryBook.book_id)
        .where(LibraryBook.id == library_book_id)
    )


async def series_ranking(
    session: AsyncSession,
    library_id: int,
    library_book_id: int,
    *,
    within: Select | None = None,
    depth: int = RELATED_DEPTH,
) -> list[int]:
    """기준 책과 공식 서지의 시리즈 키가 겹치는 책. 표시 서명의 서명 정렬 순서, id 순이다."""
    keys = await _base_value(session, library_id, library_book_id, Book.series_keys)
    if not keys:
        return []
    overlap = Book.series_keys.op("&&")(literal(list(keys), ARRAY(Text)))
    return await _in_title_order(session, library_id, within, library_book_id, depth, overlap)


def kdc_three(value: str | None) -> str | None:
    """KDC 앞 세 자리. `813.72` → `813`. KDC가 아니면 None이다."""
    key = kdc_key(value)
    match = re.match(_KDC_THREE, key) if key else None
    return match.group() if match else None


def _kdc_ids(library_id: int, condition, within: Select | None) -> Select:
    query = (
        select(LibraryBook.id)
        .outerjoin(Book, Book.id == LibraryBook.book_id)
        .where(LibraryBook.library_id == library_id, condition)
    )
    return query.where(LibraryBook.id.in_(within)) if within is not None else query


async def _kdc_part(
    session: AsyncSession,
    library_id: int,
    library_book_id: int,
    condition,
    *,
    within: Select | None,
    depth: int,
    order: KdcOrder,
    model_name: str | None,
    weights: Mapping[TextKind, float] | None,
) -> list[int]:
    if order == "vector":
        if model_name is None:
            raise ValueError("KDC 벡터 순서에는 모델 이름이 필요하다")
        return await neighbor_ranking(
            session,
            model_name,
            library_id,
            library_book_id,
            within=_kdc_ids(library_id, condition, within),
            depth=depth,
            weights=weights,
        )
    return await _in_title_order(session, library_id, within, library_book_id, depth, condition)


async def kdc_ranking(
    session: AsyncSession,
    library_id: int,
    library_book_id: int,
    *,
    within: Select | None = None,
    depth: int = RELATED_DEPTH,
    level: KdcLevel = "section",
    order: KdcOrder = "title",
    model_name: str | None = None,
    weights: Mapping[TextKind, float] | None = None,
) -> list[int]:
    """기준 책과 KDC가 같은 단위인 책. KDC는 표시 값이다.

    단위: `section` 세목(소수점 첫째 자리까지, 없으면 세 자리), `three` 앞 세 자리, `nested` 같은
    세목을 먼저 두고 그다음 세 자리만 같은 책. 순서: `title` 서명 정렬 순서, `vector` 기준 책 저장
    벡터와 가까운 순서(model_name이 필요하다).
    """
    value = await _base_value(session, library_id, library_book_id, _KDC_SHOWN)
    section, three = kdc_section(value), kdc_three(value)
    if section is None or three is None:
        return []
    same_section = func.substring(_KDC_SHOWN, _KDC_SECTION) == section
    same_three = func.substring(_KDC_SHOWN, _KDC_THREE) == three
    part = {
        "within": within,
        "depth": depth,
        "order": order,
        "model_name": model_name,
        "weights": weights,
    }
    if level == "section":
        return await _kdc_part(session, library_id, library_book_id, same_section, **part)
    if level == "three":
        return await _kdc_part(session, library_id, library_book_id, same_three, **part)
    first = await _kdc_part(session, library_id, library_book_id, same_section, **part)
    if len(first) >= depth:
        return first
    rest = await _kdc_part(session, library_id, library_book_id, same_three & ~same_section, **part)
    return [*first, *rest][:depth]


async def author_ranking(
    session: AsyncSession,
    library_id: int,
    library_book_id: int,
    *,
    within: Select | None = None,
    depth: int = RELATED_DEPTH,
) -> list[int]:
    """같은 저자 조회(`same_author_books`)의 순위."""
    books = await same_author_books(
        session, library_id, library_book_id, limit=depth, within=within
    )
    return [book.id for book in books]


async def neighbor_ranking(
    session: AsyncSession,
    model_name: str,
    library_id: int,
    library_book_id: int,
    *,
    within: Select | None = None,
    depth: int = RELATED_DEPTH,
    weights: Mapping[TextKind, float] | None = None,
) -> list[int]:
    """기준 책의 저장된 벡터와 가까운 책. 기준 책에 그 종류의 벡터가 없으면 비어 있다."""
    await get_owned(session, LibraryBook, library_id, library_book_id, label=LABEL)
    found = await neighbors_of(
        session,
        model_name,
        library_id=library_id,
        library_book_ids=[library_book_id],
        limit=depth,
        weights=weights,
        within=within,
    )
    return [f.library_book.id for f in found]


def _same_category(library_id: int, category: str, within: Select | None) -> Select:
    """그 기관에서 공식 서지의 외부 분류 원문이 같은 기관 도서 id."""
    query = (
        select(LibraryBook.id)
        .join(Book, Book.id == LibraryBook.book_id)
        .where(LibraryBook.library_id == library_id, Book.external_category == category)
    )
    return query.where(LibraryBook.id.in_(within)) if within is not None else query


async def category_ranking(
    session: AsyncSession,
    model_name: str,
    library_id: int,
    library_book_id: int,
    *,
    within: Select | None = None,
    depth: int = RELATED_DEPTH,
    weights: Mapping[TextKind, float] | None = None,
) -> list[int]:
    """기준 책과 외부 분류 원문이 같은 책을 기준 책 벡터와 가까운 순서로.

    외부 분류는 상위 분야라 KDC 세목 대신으로 쓰지 않는다. 분야 안으로 좁힌 벡터 이웃이다.
    """
    category = await _base_value(session, library_id, library_book_id, Book.external_category)
    if not category:
        return []
    return await neighbor_ranking(
        session,
        model_name,
        library_id,
        library_book_id,
        within=_same_category(library_id, category, within),
        depth=depth,
        weights=weights,
    )


class LoanSignals(Protocol):
    """정보나루 대출 신호의 ISBN 순위를 주는 쪽. 실험은 파일, 제품은 (채택되면) 운영자 층 테이블."""

    async def co_loans(self, isbn: str, kind: str = CO_LOAN) -> Sequence[str]:
        """ISBN의 함께 대출(또는 마니아·다독자) ISBN 순위. 없으면 빈 목록이다."""
        ...

    async def popular(self, age_group: str) -> Sequence[str]:
        """연령 묶음의 정보나루 인기 ISBN 순위. 없으면 빈 목록이다."""
        ...


async def held_ranking(
    session: AsyncSession,
    library_id: int,
    isbns: Sequence[str],
    *,
    within: Select | None = None,
    depth: int = RELATED_DEPTH,
    exclude: Sequence[int] = (),
) -> list[int]:
    """ISBN 순위에서 그 기관이 가진 추천 가능한 책만 넘긴 순서대로 남긴다.

    ISBN은 연결된 공식 서지의 ISBN이 먼저, 없으면 기관 도서의 ISBN이다.
    """
    order = {isbn: position for position, isbn in reversed(list(enumerate(isbns)))}
    if not order:
        return []
    rows = await session.execute(
        select(LibraryBook.id, _ISBN_SHOWN)
        .outerjoin(Book, Book.id == LibraryBook.book_id)
        .where(*_scope(library_id, within, exclude), _ISBN_SHOWN.in_(list(order)))
    )
    held = sorted(rows.all(), key=lambda row: (order[row[1]], row[0]))
    return [book_id for book_id, _ in held][:depth]


async def co_loan_ranking(
    session: AsyncSession,
    library_id: int,
    library_book_id: int,
    loan_signals: LoanSignals | None,
    *,
    within: Select | None = None,
    depth: int = RELATED_DEPTH,
    kind: str = CO_LOAN,
) -> list[int]:
    """함께 대출 신호: 기준 책 ISBN의 함께 대출 순위에서 그 기관이 가진 추천 가능한 책.

    기준 책에 ISBN이 없거나 순위를 주는 쪽이 없으면 비어 있다.
    """
    isbn = await _base_value(session, library_id, library_book_id, _ISBN_SHOWN)
    if isbn is None or loan_signals is None:
        return []
    isbns = await loan_signals.co_loans(isbn, kind)
    return await held_ranking(
        session, library_id, isbns, within=within, depth=depth, exclude=[library_book_id]
    )


async def editions_of(
    session: AsyncSession, library_id: int, library_book_ids: Sequence[int]
) -> set[int]:
    """기준 책들의 다른 판본(기준 책은 빼고). 그 기관의 책만 본다.

    판본·묶음 표기를 지운 표시 서명에서 공백과 문장부호를 지운 값이 같고 지은이가 한 명 이상
    겹치면 같은 책이다(`코스모스`와 `코스모스 (특별판)`, `총 균 쇠`와 `총, 균, 쇠`).
    """
    keys = writer_keys_sql().label("keys")
    bases = (
        await session.execute(
            select(LibraryBook.id, _TITLE, keys)
            .outerjoin(Book, Book.id == LibraryBook.book_id)
            .where(LibraryBook.library_id == library_id, LibraryBook.id.in_(list(library_book_ids)))
        )
    ).all()
    wanted = sorted({key for _, _, base_keys in bases for key in base_keys or ()})
    if not wanted:
        return set()
    rows = await session.execute(
        select(LibraryBook.id, _TITLE, keys)
        .outerjoin(Book, Book.id == LibraryBook.book_id)
        .where(
            LibraryBook.library_id == library_id,
            LibraryBook.id.not_in([base_id for base_id, _, _ in bases]),
            writer_keys_sql().op("&&")(literal(wanted, ARRAY(Text))),
        )
    )
    titles = [(match_key(strip_edition(title)), set(found or ())) for _, title, found in bases]
    return {
        book_id
        for book_id, title, book_keys in rows
        if any(
            match_key(strip_edition(title)) == base_title and base_keys & set(book_keys or ())
            for base_title, base_keys in titles
        )
    }


def _default_signals() -> dict[str, float]:
    return {SERIES: 1.0, AUTHOR: 1.0, KDC: 1.0, VECTOR: 1.0}


@dataclass(frozen=True)
class SimilarSettings:
    signals: Mapping[str, float] = field(default_factory=_default_signals)  # 신호 → 가중치(0은 끔)
    fusion: Literal["rrf", "priority"] = "rrf"  # priority: order대로 앞 신호의 책을 먼저
    order: Sequence[str] = (SERIES, AUTHOR, KDC, VECTOR)
    weights: Mapping[TextKind, float] = field(default_factory=lambda: {TextKind.FULL: 1.0})
    category_scope: bool = False  # 벡터 이웃을 같은 외부 분류 안으로 좁힌다
    kdc_level: KdcLevel = "section"  # 같은 KDC의 단위
    kdc_order: KdcOrder = "title"  # 같은 단위 안의 순서
    kdc_scope: bool = False  # 진단: 벡터 이웃을 같은 KDC 단위 안으로 좁힌다
    depth: int = RELATED_DEPTH
    rrf_k: int = RRF_K
    series_cap: int | None = None
    mmr_lambda: float | None = None
    limit: int = RELATED_LIMIT


def fuse_priority(rankings: Mapping[str, Sequence[int]], order: Sequence[str]) -> list[Ranked]:
    """order의 신호 순서대로 앞 신호의 책을 먼저 둔다. 한 번 나온 책은 다시 넣지 않는다.

    점수는 순서를 나타내는 값(1/위치)이다. 근거는 그 책이 오른 모든 신호의 순위다.
    """
    ranks: dict[int, dict[str, int]] = {}
    merged: list[int] = []
    for signal in [*order, *(name for name in rankings if name not in order)]:
        for position, book_id in enumerate(rankings.get(signal, ()), start=1):
            if book_id not in ranks:
                merged.append(book_id)
            ranks.setdefault(book_id, {}).setdefault(signal, position)
    return [
        Ranked(book_id, 1 / position, ranks[book_id])
        for position, book_id in enumerate(merged, start=1)
    ]


async def _series_keys(
    session: AsyncSession, library_id: int, ids: Sequence[int]
) -> dict[int, list[str]]:
    rows = await session.execute(
        select(LibraryBook.id, Book.series_keys)
        .join(Book, Book.id == LibraryBook.book_id)
        .where(LibraryBook.library_id == library_id, LibraryBook.id.in_(list(ids)))
    )
    return {book_id: list(keys) for book_id, keys in rows if keys}


async def _diversify(
    session: AsyncSession,
    model_name: str,
    library_id: int,
    ranked: list[Ranked],
    series_cap: int | None,
    mmr_lambda: float | None,
) -> list[Ranked]:
    ids = [item.library_book_id for item in ranked]
    if series_cap is not None and ids:
        ranked = cap_series(ranked, await _series_keys(session, library_id, ids), series_cap)
    if mmr_lambda is not None and len(ranked) > 1:
        vectors = await book_vectors(
            session, model_name, library_id, [item.library_book_id for item in ranked]
        )
        ranked = mmr(ranked, vectors, mmr_lambda)
    return ranked


async def kdc_scoped_ranking(
    session: AsyncSession,
    model_name: str,
    library_id: int,
    library_book_id: int,
    settings: SimilarSettings,
    *,
    within: Select | None = None,
    depth: int = RELATED_DEPTH,
) -> list[int]:
    """진단: 벡터 이웃을 기준 책과 같은 KDC 단위 안으로 좁힌다. KDC가 없으면 비어 있다."""
    return await kdc_ranking(
        session,
        library_id,
        library_book_id,
        within=within,
        depth=depth,
        level=settings.kdc_level,
        order="vector",
        model_name=model_name,
        weights=settings.weights,
    )


async def similar_rankings(
    session: AsyncSession,
    model_name: str,
    *,
    library_id: int,
    library_book_id: int,
    within: Select | None = None,
    settings: SimilarSettings | None = None,
    exclude: Sequence[int] = (),
    loan_signals: LoanSignals | None = None,
) -> dict[str, list[int]]:
    """설정에서 켠 신호별 순위. 기준 책과 그 다른 판본, exclude의 책은 뺀다.

    다른 기관의 기준 책은 NotFoundError다.
    """
    settings = settings or SimilarSettings()
    await get_owned(session, LibraryBook, library_id, library_book_id, label=LABEL)
    on = {name for name, weight in settings.signals.items() if weight > 0}
    scope = {"within": within, "depth": settings.depth}
    rankings: dict[str, list[int]] = {}
    if SERIES in on:
        rankings[SERIES] = await series_ranking(session, library_id, library_book_id, **scope)
    if AUTHOR in on:
        rankings[AUTHOR] = await author_ranking(session, library_id, library_book_id, **scope)
    if KDC in on:
        rankings[KDC] = await kdc_ranking(
            session,
            library_id,
            library_book_id,
            level=settings.kdc_level,
            order=settings.kdc_order,
            model_name=model_name,
            weights=settings.weights,
            **scope,
        )
    if VECTOR in on and settings.kdc_scope:
        rankings[VECTOR] = await kdc_scoped_ranking(
            session, model_name, library_id, library_book_id, settings, **scope
        )
    elif VECTOR in on:
        nearest = category_ranking if settings.category_scope else neighbor_ranking
        rankings[VECTOR] = await nearest(
            session, model_name, library_id, library_book_id, weights=settings.weights, **scope
        )
    for kind in LOAN_KINDS:
        if kind in on:
            rankings[kind] = await co_loan_ranking(
                session, library_id, library_book_id, loan_signals, kind=kind, **scope
            )
    hidden = {*exclude, *(await editions_of(session, library_id, [library_book_id, *exclude]))}
    return {
        name: [book_id for book_id in ranking if book_id not in hidden]
        for name, ranking in rankings.items()
    }


def _fuse(rankings: Mapping[str, Sequence[int]], settings: SimilarSettings) -> list[Ranked]:
    if settings.fusion == "priority":
        return fuse_priority(rankings, settings.order)
    return fuse_rrf(rankings, k=settings.rrf_k, weights=settings.signals)


async def find_similar(
    session: AsyncSession,
    model_name: str,
    *,
    library_id: int,
    library_book_id: int,
    within: Select | None = None,
    settings: SimilarSettings | None = None,
    loan_signals: LoanSignals | None = None,
) -> list[Ranked]:
    """기준 책과 비슷한, 그 기관의 추천 가능한 책. 결과마다 신호별 순위(근거)가 있다.

    model_name은 벡터를 적재한 인코더의 모델 이름이다(질의를 인코딩하지 않는다). 같은 데이터·
    기준 책·설정이면 같은 결과다.
    """
    settings = settings or SimilarSettings()
    rankings = await similar_rankings(
        session,
        model_name,
        library_id=library_id,
        library_book_id=library_book_id,
        within=within,
        settings=settings,
        loan_signals=loan_signals,
    )
    ranked = await _diversify(
        session,
        model_name,
        library_id,
        _fuse(rankings, settings),
        settings.series_cap,
        settings.mmr_lambda,
    )
    return ranked[: settings.limit]


async def popular_ranking(
    session: AsyncSession,
    library_id: int,
    *,
    within: Select | None = None,
    days: int = POPULAR_DAYS,
    depth: int = RELATED_DEPTH,
    exclude: Sequence[int] = (),
) -> list[int]:
    """우리 도서관 인기: 최근 days일(기관 시간대 오늘 기준) 대출 행 수가 많은 추천 가능한 책.

    같으면 표시 서명의 서명 정렬 순서, id 순이다. 그 기관의 대출만 센다. 대출 행이 없으면 비어 있다.
    """
    loans = func.count(Loan.id)
    rows = await session.execute(
        select(LibraryBook.id)
        .join(
            Holding,
            (Holding.library_id == LibraryBook.library_id)
            & (Holding.library_book_id == LibraryBook.id),
        )
        .join(Loan, (Loan.library_id == Holding.library_id) & (Loan.holding_id == Holding.id))
        .outerjoin(Book, Book.id == LibraryBook.book_id)
        .where(
            *_scope(library_id, within, exclude),
            Loan.library_id == library_id,
            Loan.loaned_on >= clock.today() - timedelta(days=days),
        )
        .group_by(LibraryBook.id, _TITLE)
        .order_by(loans.desc(), korean_order(_TITLE), LibraryBook.id)
        .limit(depth)
    )
    return list(rows.scalars())


async def national_popular_ranking(
    session: AsyncSession,
    library_id: int,
    loan_signals: LoanSignals | None,
    *,
    age_group: str = POPULAR_ALL,
    within: Select | None = None,
    depth: int = RELATED_DEPTH,
    exclude: Sequence[int] = (),
) -> list[int]:
    """정보나루 인기: 연령 묶음의 전국 인기 ISBN 순위에서 그 기관이 가진 추천 가능한 책."""
    if loan_signals is None:
        return []
    isbns = await loan_signals.popular(age_group)
    return await held_ranking(
        session, library_id, isbns, within=within, depth=depth, exclude=exclude
    )


def _default_history_signals() -> dict[str, float]:
    return {VECTOR: 1.0}


@dataclass(frozen=True)
class HistorySettings:
    # 2026-11-16 추천 실험: 벡터 평균이 책별 RRF(k 60)를 모든 기록에서 이겼다. 책별 순위를 k 60으로
    # 합치면 여러 목록에 중간 순위로 겹치는 책이 각 책의 가장 가까운 책보다 위로 온다
    method: Literal["mean", "per-book"] = "mean"
    similar: SimilarSettings = field(default_factory=SimilarSettings)  # per-book: 책마다 쓰는 설정
    weights: Mapping[TextKind, float] = field(default_factory=lambda: {TextKind.FULL: 1.0})
    # mean: 벡터 평균 순위와 RRF로 합칠 기록 신호(`kdc`, `author`, `co_loan`) → 가중치
    signals: Mapping[str, float] = field(default_factory=_default_history_signals)
    kdc_level: KdcLevel = "section"  # 기록 신호 `kdc`의 단위
    depth: int = RELATED_DEPTH
    rrf_k: int = RRF_K
    series_cap: int | None = None
    mmr_lambda: float | None = None
    popular_fill: bool = True  # 결과가 limit보다 적으면 우리 도서관 인기, 정보나루 인기로 채운다
    popular_days: int = POPULAR_DAYS
    limit: int = RELATED_LIMIT


async def _vector_order(
    session: AsyncSession,
    model_name: str,
    library_id: int,
    bases: Sequence[int],
    candidates: Sequence[int],
    weights: Mapping[TextKind, float],
) -> dict[int, int]:
    """후보들의 기록 벡터 평균 이웃 순서(벡터 없는 후보는 없음)."""
    if not candidates:
        return {}
    found = await neighbors_of(
        session,
        model_name,
        library_id=library_id,
        library_book_ids=bases,
        limit=len(candidates),
        weights=weights,
        within=select(LibraryBook.id).where(LibraryBook.id.in_(list(candidates))),
    )
    return {f.library_book.id: position for position, f in enumerate(found)}


async def _count_ranking(
    session: AsyncSession,
    model_name: str,
    library_id: int,
    bases: Sequence[int],
    counts: Mapping[int, tuple[int, ...]],
    weights: Mapping[TextKind, float],
    depth: int,
) -> list[int]:
    """겹치는 수가 많은 순, 같으면 기록 벡터 평균과 가까운 순, 벡터가 없으면 id 순."""
    nearest = await _vector_order(session, model_name, library_id, bases, list(counts), weights)
    far = len(nearest)
    ordered = sorted(
        counts,
        key=lambda book_id: (
            tuple(-c for c in counts[book_id]),
            nearest.get(book_id, far),
            book_id,
        ),
    )
    return ordered[:depth]


async def history_kdc_ranking(
    session: AsyncSession,
    model_name: str,
    library_id: int,
    bases: Sequence[int],
    *,
    level: KdcLevel = "section",
    within: Select | None = None,
    exclude: Sequence[int] = (),
    weights: Mapping[TextKind, float] | None = None,
    depth: int = RELATED_DEPTH,
) -> list[int]:
    """기록 신호 같은 KDC: 기록 책들의 KDC와 같은 단위인 책. 겹치는 기록 책이 많은 순."""
    rows = await session.execute(
        select(LibraryBook.id, _KDC_SHOWN)
        .outerjoin(Book, Book.id == LibraryBook.book_id)
        .where(LibraryBook.library_id == library_id, LibraryBook.id.in_(list(bases)))
    )
    base_keys = [(kdc_section(value), kdc_three(value)) for _, value in rows if kdc_three(value)]
    if not base_keys:
        return []
    threes = sorted({three for _, three in base_keys})
    rows = await session.execute(
        select(LibraryBook.id, _KDC_SHOWN)
        .outerjoin(Book, Book.id == LibraryBook.book_id)
        .where(
            *_scope(library_id, within, [*bases, *exclude]),
            func.substring(_KDC_SHOWN, _KDC_THREE).in_(threes),
        )
    )
    counts: dict[int, tuple[int, ...]] = {}
    for book_id, value in rows:
        section, three = kdc_section(value), kdc_three(value)
        by_section = sum(1 for base_section, _ in base_keys if base_section == section)
        by_three = sum(1 for _, base_three in base_keys if base_three == three)
        if level == "section" and by_section:
            counts[book_id] = (by_section,)
        elif level == "three":
            counts[book_id] = (by_three,)
        elif level == "nested":
            counts[book_id] = (by_section, by_three)
    weights = weights or {TextKind.FULL: 1.0}
    return await _count_ranking(session, model_name, library_id, bases, counts, weights, depth)


async def history_author_ranking(
    session: AsyncSession,
    model_name: str,
    library_id: int,
    bases: Sequence[int],
    *,
    within: Select | None = None,
    exclude: Sequence[int] = (),
    weights: Mapping[TextKind, float] | None = None,
    depth: int = RELATED_DEPTH,
) -> list[int]:
    """기록 신호 겹치는 저자: 기록 책들의 지은이와 겹치는 책. 겹치는 지은이가 많은 순."""
    keys = writer_keys_sql()
    found = await session.scalars(
        select(keys).where(LibraryBook.library_id == library_id, LibraryBook.id.in_(list(bases)))
    )
    wanted = sorted({key for book_keys in found for key in book_keys or ()})
    if not wanted:
        return []
    rows = await session.execute(
        select(LibraryBook.id, keys).where(
            *_scope(library_id, within, [*bases, *exclude]),
            keys.op("&&")(literal(wanted, ARRAY(Text))),
        )
    )
    counts = {book_id: (len(set(wanted) & set(book_keys or ())),) for book_id, book_keys in rows}
    weights = weights or {TextKind.FULL: 1.0}
    return await _count_ranking(session, model_name, library_id, bases, counts, weights, depth)


async def history_co_loan_ranking(
    session: AsyncSession,
    library_id: int,
    bases: Sequence[int],
    loan_signals: LoanSignals | None,
    *,
    within: Select | None = None,
    exclude: Sequence[int] = (),
    depth: int = RELATED_DEPTH,
    rrf_k: int = RRF_K,
) -> list[int]:
    """기록 신호 함께 대출: 기록 책마다의 함께 대출 신호를 RRF로 합친 순위."""
    hidden = {*bases, *exclude}
    each: dict[str, list[int]] = {}
    for base_id in bases:
        ranking = await co_loan_ranking(
            session, library_id, base_id, loan_signals, within=within, depth=depth
        )
        each[f"{BOOK_SIGNAL}{base_id}"] = [book_id for book_id in ranking if book_id not in hidden]
    return [item.library_book_id for item in fuse_rrf(each, k=rrf_k)][:depth]


async def find_from_history(
    session: AsyncSession,
    model_name: str,
    *,
    library_id: int,
    library_book_ids: Sequence[int],
    within: Select | None = None,
    settings: HistorySettings | None = None,
    loan_signals: LoanSignals | None = None,
    popular_group: str = POPULAR_ALL,
) -> list[Ranked]:
    """최근 기록의 책들에서 그 기관의 추천 가능한 책을 고른다.

    기록 책 중 그 기관의 책만 근거로 쓴다(없는 id와 다른 기관의 id는 건너뛴다). 기록 책과 그 다른
    판본은 결과에 없다. `mean`은 기록 책 벡터의 평균과 가까운 순서(켠 기록 신호와 RRF로 합친다),
    `per-book`은 책마다 만든 비슷한 책 순위를 RRF로 합친 순서다(근거 이름은 `book:<기록 책 id>`).
    모자라면 우리 도서관 인기, 그다음 정보나루 인기(`popular_group` 연령 묶음)로 채운다. 기록이
    비어 있으면 인기로만 채운다.
    """
    settings = settings or HistorySettings()
    wanted = list(dict.fromkeys(library_book_ids))
    owned = set(
        await session.scalars(
            select(LibraryBook.id).where(
                LibraryBook.library_id == library_id, LibraryBook.id.in_(wanted)
            )
        )
    )
    bases = [book_id for book_id in wanted if book_id in owned]
    hidden = {*bases, *(await editions_of(session, library_id, bases))} if bases else set()
    rankings: dict[str, list[int]] = {}
    weights: Mapping[str, float] | None = None
    if bases and settings.method == "mean":
        on = {name for name, weight in settings.signals.items() if weight > 0}
        weights = settings.signals
        common = {"within": within, "exclude": sorted(hidden), "depth": settings.depth}
        if VECTOR in on:
            found = await neighbors_of(
                session,
                model_name,
                library_id=library_id,
                library_book_ids=bases,
                limit=settings.depth + len(hidden),
                weights=settings.weights,
                within=within,
            )
            ids = [f.library_book.id for f in found if f.library_book.id not in hidden]
            rankings[VECTOR] = ids[: settings.depth]
        if KDC in on:
            rankings[KDC] = await history_kdc_ranking(
                session,
                model_name,
                library_id,
                bases,
                level=settings.kdc_level,
                weights=settings.weights,
                **common,
            )
        if AUTHOR in on:
            rankings[AUTHOR] = await history_author_ranking(
                session, model_name, library_id, bases, weights=settings.weights, **common
            )
        if CO_LOAN in on:
            rankings[CO_LOAN] = await history_co_loan_ranking(
                session, library_id, bases, loan_signals, rrf_k=settings.rrf_k, **common
            )
    elif bases:
        each = replace(settings.similar, depth=settings.depth, series_cap=None, mmr_lambda=None)
        for base_id in bases:
            signals = await similar_rankings(
                session,
                model_name,
                library_id=library_id,
                library_book_id=base_id,
                within=within,
                settings=each,
                exclude=sorted(hidden),
                loan_signals=loan_signals,
            )
            ranked = _fuse(signals, each)[: settings.depth]
            rankings[f"{BOOK_SIGNAL}{base_id}"] = [item.library_book_id for item in ranked]
    ranked = await _diversify(
        session,
        model_name,
        library_id,
        fuse_rrf(rankings, k=settings.rrf_k, weights=weights),
        settings.series_cap,
        settings.mmr_lambda,
    )
    ranked = ranked[: settings.limit]
    if settings.popular_fill and len(ranked) < settings.limit:
        ranked += await _popular_fill(
            session,
            library_id,
            settings,
            loan_signals,
            popular_group=popular_group,
            within=within,
            taken={*hidden, *(item.library_book_id for item in ranked)},
            wanted=settings.limit - len(ranked),
        )
    return ranked


async def _popular_fill(
    session: AsyncSession,
    library_id: int,
    settings: HistorySettings,
    loan_signals: LoanSignals | None,
    *,
    popular_group: str,
    within: Select | None,
    taken: set[int],
    wanted: int,
) -> list[Ranked]:
    """우리 도서관 인기로 먼저, 모자라면 정보나루 인기로 뒤를 채운다."""
    ours = await popular_ranking(
        session,
        library_id,
        within=within,
        days=settings.popular_days,
        depth=wanted,
        exclude=sorted(taken),
    )
    filled = [
        Ranked(book_id, 0.0, {POPULAR: position}) for position, book_id in enumerate(ours, start=1)
    ]
    if len(filled) < wanted:
        national = await national_popular_ranking(
            session,
            library_id,
            loan_signals,
            age_group=popular_group,
            within=within,
            depth=wanted - len(filled),
            exclude=sorted({*taken, *ours}),
        )
        filled += [
            Ranked(book_id, 0.0, {NATIONAL_POPULAR: position})
            for position, book_id in enumerate(national, start=1)
        ]
    return filled
