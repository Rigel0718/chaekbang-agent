"""[catalog/related-recommendation] 비슷한 책과 최근 기록 추천: 신호, 판본 제외, 합치기, 인기, 범위.

가짜 인코더로 적재하고 저장된 벡터로 조회한다(질의 인코딩 없음).
"""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.contributors import sync_contributors
from app.central.models import Book, ExternalSource
from app.central.official_embeddings import run_official_embedding
from app.core import clock
from app.core.errors import NotFoundError
from app.features.children.service import children_book_ids
from app.library.recommendation.embeddings import run_library_embedding
from app.library.recommendation.related import (
    AUTHOR,
    KDC,
    SERIES,
    VECTOR,
    HistorySettings,
    SimilarSettings,
    category_ranking,
    editions_of,
    find_from_history,
    find_similar,
    kdc_ranking,
    kdc_section,
    neighbor_ranking,
    popular_ranking,
    series_ranking,
)
from tests.conftest import Tenant
from tests.embedding_helpers import FakeEmbedder, toward, unit
from tests.helpers import add_audience, add_held_book, add_holding, add_loan, add_member

MODEL = "fake-model"
VECTOR_ONLY = SimilarSettings(signals={VECTOR: 1.0})


async def linked(session: AsyncSession, library_id: int, title: str, *statuses: str, **official):
    """공식 서지(YES24)에 연결된, 사본이 있는 기관 도서. 기여자도 채운다."""
    official.setdefault("author", f"{title} 지은이 저")
    book = await add_held_book(
        session,
        library_id,
        *statuses,
        title=title,
        official={"external_source": ExternalSource.YES24.value, **official},
    )
    await sync_contributors(
        session, await session.scalar(select(Book).where(Book.id == book["book_id"]))
    )
    return book["id"]


async def unlinked(session: AsyncSession, library_id: int, title: str, *statuses: str, **values):
    values.setdefault("author", f"{title} 지은이")
    return (await add_held_book(session, library_id, *statuses, title=title, **values))["id"]


async def load(session: AsyncSession, library_id: int, cosines: dict[str, float]) -> None:
    """서명에 든 낱말마다 `기준` 벡터(`unit(1)`)와의 유사도를 정해 두 층을 적재한다."""
    embedder = FakeEmbedder(
        MODEL, vectors={"기준": unit(1), **{word: toward(c) for word, c in cosines.items()}}
    )
    await run_official_embedding(session, embedder, full=True)
    await run_library_embedding(session, embedder, full=True, library_id=library_id)


async def similar(session: AsyncSession, library_id: int, base: int, **options) -> list[int]:
    found = await find_similar(
        session, MODEL, library_id=library_id, library_book_id=base, **options
    )
    return [item.library_book_id for item in found]


# --- 신호 ---


async def test_same_series(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 같은 시리즈 신호 / 같은 시리즈"""
    base = await linked(session, library_a.id, "흔한남매 1", series_keys=["흔한남매"])
    third = await linked(session, library_a.id, "흔한남매 3", series_keys=["흔한남매", "다른묶음"])
    second = await linked(session, library_a.id, "흔한남매 2", series_keys=["흔한남매"])
    await linked(session, library_a.id, "마법천자문 1", series_keys=["마법천자문"])
    assert await series_ranking(session, library_a.id, base) == [second, third]


async def test_base_without_series(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 같은 시리즈 신호 / 시리즈 없는 기준 책"""
    base = await unlinked(session, library_a.id, "기증받은 책")
    await linked(session, library_a.id, "흔한남매 1", series_keys=["흔한남매"])
    assert await series_ranking(session, library_a.id, base) == []


async def test_same_kdc_section(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 같은 KDC 세목 신호 / 같은 세목"""
    base = await unlinked(session, library_a.id, "기준", kdc="813.7")
    finer = await unlinked(session, library_a.id, "나", kdc="813.72")
    await unlinked(session, library_a.id, "다", kdc="813.6")
    same = await linked(session, library_a.id, "가", kdc="813.7")
    await unlinked(session, library_a.id, "라", kdc="813")
    assert await kdc_ranking(session, library_a.id, base) == [same, finer]
    assert kdc_section("813.72") == "813.7" and kdc_section("813") == "813"


async def test_base_without_kdc(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 같은 KDC 세목 신호 / KDC 없는 기준 책"""
    base = await unlinked(session, library_a.id, "기준")
    await unlinked(session, library_a.id, "나", kdc="813.7")
    assert await kdc_ranking(session, library_a.id, base) == []


async def test_same_external_category(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 같은 외부 분류 신호 / 같은 외부 분류"""
    essay = {"external_category": "국내도서-에세이"}
    base = await linked(session, library_a.id, "기준", **essay)
    far = await linked(session, library_a.id, "먼수필", **essay)
    near = await linked(session, library_a.id, "가까운수필", **essay)
    await linked(session, library_a.id, "인문책", external_category="국내도서-인문")
    await load(session, library_a.id, {"먼수필": 0.2, "가까운수필": 0.8, "인문책": 0.95})
    assert await category_ranking(session, MODEL, library_a.id, base) == [near, far]
    plain = await unlinked(session, library_a.id, "분류 없는 책")
    assert await category_ranking(session, MODEL, library_a.id, plain) == []


async def test_vector_neighbors_in_order(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 벡터 이웃 신호 / 가까운 순서"""
    base = await unlinked(session, library_a.id, "기준")
    c = await unlinked(session, library_a.id, "씨책")
    b = await linked(session, library_a.id, "비책")
    await load(session, library_a.id, {"비책": 0.9, "씨책": 0.5})
    assert await neighbor_ranking(session, MODEL, library_a.id, base) == [b, c]


async def test_base_without_vector(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 벡터 이웃 신호 / 벡터 없는 기준 책"""
    await unlinked(session, library_a.id, "비책")
    await load(session, library_a.id, {"비책": 0.9})
    late = await unlinked(session, library_a.id, "적재 뒤에 들어온 기준")
    assert await neighbor_ranking(session, MODEL, library_a.id, late) == []
    assert await similar(session, library_a.id, late, settings=VECTOR_ONLY) == []


# --- 판본 ---


async def test_other_edition_is_left_out(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 기준 책과 다른 판본 제외 / 개정판"""
    base = await linked(session, library_a.id, "코스모스 기준", author="칼 세이건 저/홍승수 역")
    special = await linked(
        session, library_a.id, "코스모스 기준 (특별판)", author="칼 세이건 저/홍승수 역"
    )
    spaced = await unlinked(session, library_a.id, "코스모스, 기준", author="칼 세이건 지음")
    other = await linked(session, library_a.id, "창백한 푸른 점", author="칼 세이건 저")
    await load(session, library_a.id, {"특별판": 0.99, "창백한": 0.5})
    assert await editions_of(session, library_a.id, [base]) == {special, spaced}
    assert await similar(session, library_a.id, base) == [other]


async def test_same_title_by_another_writer_stays(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 기준 책과 다른 판본 제외 / 서명만 같은 다른 책"""
    base = await linked(session, library_a.id, "기준 여행", author="김하나 저")
    namesake = await linked(session, library_a.id, "기준 여행", author="이둘 저")
    await load(session, library_a.id, {})
    assert await editions_of(session, library_a.id, [base]) == set()
    assert await similar(session, library_a.id, base, settings=VECTOR_ONLY) == [namesake]


# --- 합치기 ---


async def _mixed_signals(session: AsyncSession, library_id: int) -> dict[str, int]:
    writer = "한작가 저"
    ids = {
        "base": await linked(
            session, library_id, "기준", author=writer, series_keys=["묶음"], kdc="813.7"
        ),
        "series": await linked(session, library_id, "시리즈책", series_keys=["묶음"]),
        "author": await linked(session, library_id, "작가책", author=writer),
        "near": await linked(session, library_id, "가까운책"),
        "far": await unlinked(session, library_id, "먼책"),
    }
    await load(session, library_id, {"시리즈책": 0.1, "작가책": 0.3, "가까운책": 0.9, "먼책": 0.2})
    return ids


async def test_evidence(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 신호 합치기와 근거 / 근거"""
    ids = await _mixed_signals(session, library_a.id)
    found = await find_similar(session, MODEL, library_id=library_a.id, library_book_id=ids["base"])
    ranks = {item.library_book_id: dict(item.ranks) for item in found}
    assert ranks[ids["author"]] == {AUTHOR: 1, VECTOR: 2}
    assert ranks[ids["series"]] == {SERIES: 1, VECTOR: 4}
    assert ranks[ids["near"]] == {VECTOR: 1}
    # 두 신호에 오른 책이 벡터 1위만인 책보다 먼저다
    assert [item.library_book_id for item in found][:2] == [ids["author"], ids["series"]]


async def test_rule_signals_first(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 신호 합치기와 근거 / 규칙 신호 먼저"""
    ids = await _mixed_signals(session, library_a.id)
    settings = SimilarSettings(fusion="priority", order=(SERIES, AUTHOR, KDC, VECTOR))
    found = await find_similar(
        session, MODEL, library_id=library_a.id, library_book_id=ids["base"], settings=settings
    )
    assert [item.library_book_id for item in found] == [
        ids["series"],
        ids["author"],
        ids["near"],
        ids["far"],
    ]
    assert dict(found[1].ranks) == {AUTHOR: 1, VECTOR: 2}


async def test_all_signals_empty(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 신호 합치기와 근거 / 신호가 모두 비어 있음"""
    base = await unlinked(session, library_a.id, "홀로 있는 책")
    await unlinked(session, library_a.id, "벡터 없는 다른 책")
    assert await similar(session, library_a.id, base) == []


# --- 최근 기록 ---


async def test_history_fuses_per_book_rankings(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 최근 기록 합치기 / 책별 순위 합치기"""
    a = await unlinked(session, library_a.id, "에이책")
    b = await unlinked(session, library_a.id, "비책")
    x = await unlinked(session, library_a.id, "엑스책")
    y = await unlinked(session, library_a.id, "와이책")
    embedder = FakeEmbedder(
        MODEL,
        vectors={
            "에이책": unit(1, 0, 0),
            "비책": unit(0, 1, 0),
            "엑스책": unit(1, 0.6, 0),  # A의 1위, B의 2위
            "와이책": unit(0, 1, 0.5),  # B의 1위, A와는 직교
        },
    )
    await run_library_embedding(session, embedder, full=True, library_id=library_a.id)
    settings = HistorySettings(method="per-book", similar=VECTOR_ONLY)
    found = await find_from_history(
        session, MODEL, library_id=library_a.id, library_book_ids=[a, b], settings=settings
    )
    assert [item.library_book_id for item in found] == [x, y]
    assert dict(found[0].ranks) == {f"book:{a}": 1, f"book:{b}": 2}
    mean = await find_from_history(
        session,
        MODEL,
        library_id=library_a.id,
        library_book_ids=[a, b],
        settings=HistorySettings(method="mean"),
    )
    assert [item.library_book_id for item in mean] == [x, y]
    assert a not in {item.library_book_id for item in mean}


async def test_history_ignores_other_library_books(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/related-recommendation] 최근 기록 합치기 / 다른 기관의 기록 책"""
    mine = await unlinked(session, library_a.id, "기준 우리책")
    near = await unlinked(session, library_a.id, "우리이웃")
    theirs = await unlinked(session, library_b.id, "기준 남의책")
    their_near = await unlinked(session, library_b.id, "남의이웃")
    embedder = FakeEmbedder(
        MODEL, vectors={"기준": unit(1), "우리이웃": toward(0.5), "남의이웃": toward(0.9)}
    )
    for library in (library_a, library_b):
        await run_library_embedding(session, embedder, full=True, library_id=library.id)
    for method in ("mean", "per-book"):
        only = await find_from_history(
            session,
            MODEL,
            library_id=library_a.id,
            library_book_ids=[theirs],
            settings=HistorySettings(method=method),
        )
        assert only == []
        both = await find_from_history(
            session,
            MODEL,
            library_id=library_a.id,
            library_book_ids=[theirs, mine],
            settings=HistorySettings(method=method),
        )
        assert [item.library_book_id for item in both] == [near]
        assert their_near not in {item.library_book_id for item in both}
        assert all(f"book:{theirs}" not in item.ranks for item in both)


# --- 인기 ---


async def _loaned(session: AsyncSession, library_id: int, title: str, days_ago: list[int]) -> int:
    """대출 기록이 days_ago만큼 있는(모두 반납) 책."""
    book = await add_held_book(session, library_id, title=title)
    member = await add_member(session, library_id, f"M{book['id']}")
    for n, ago in enumerate(days_ago):
        holding = await add_holding(session, library_id, book["id"], f"LN{book['id']}-{n}")
        day = clock.today() - timedelta(days=ago)
        await add_loan(session, holding, member, loaned_on=day, returned_on=day)
    return book["id"]


async def test_popular_by_recent_loans(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 우리 도서관 인기 / 대출 수 순서"""
    b = await _loaned(session, library_a.id, "비책", [10])
    a = await _loaned(session, library_a.id, "에이책", [1, 30, 180])
    await _loaned(session, library_a.id, "씨책", [200, 201, 250, 300, 400])
    tie = await _loaned(session, library_a.id, "가책", [5])
    await add_held_book(session, library_a.id, title="안 빌린 책")
    assert await popular_ranking(session, library_a.id) == [a, tie, b]


async def test_popular_counts_own_library_only(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/related-recommendation] 우리 도서관 인기 / 다른 기관의 대출"""
    await _loaned(session, library_b.id, "남의 인기책", [1, 2, 3])
    quiet = await add_held_book(session, library_a.id, title="남의 인기책")
    mine = await _loaned(session, library_a.id, "우리 책", [1])
    assert await popular_ranking(session, library_a.id) == [mine]
    assert quiet["id"] not in await popular_ranking(session, library_a.id)


async def test_popular_fills_short_history(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 우리 도서관 인기 / 기록 결과가 모자람"""
    base = await unlinked(session, library_a.id, "기준")
    near = await unlinked(session, library_a.id, "이웃하나")
    next_near = await unlinked(session, library_a.id, "이웃둘")
    await load(session, library_a.id, {"이웃하나": 0.9, "이웃둘": 0.5})
    populars = [await _loaned(session, library_a.id, f"인기{n}", [1] * (4 - n)) for n in range(4)]
    await add_loan(
        session,
        await add_holding(session, library_a.id, near, "LNX-1"),
        await add_member(session, library_a.id, "MX"),
        returned_on=clock.today(),
    )
    found = await find_from_history(
        session, MODEL, library_id=library_a.id, library_book_ids=[base]
    )
    assert [item.library_book_id for item in found] == [near, next_near, *populars[:3]]
    assert dict(found[2].ranks) == {"popular": 1}
    plain = await find_from_history(
        session,
        MODEL,
        library_id=library_a.id,
        library_book_ids=[base],
        settings=HistorySettings(popular_fill=False),
    )
    assert [item.library_book_id for item in plain] == [near, next_near]


# --- 범위 ---


async def test_children_condition_comes_first(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 비슷한 책 추천의 범위 / 어린이 조건"""
    writer = "한작가 글"
    base = await linked(session, library_a.id, "기준", author=writer)
    general = await linked(session, library_a.id, "일반서", author=writer)
    children = [await unlinked(session, library_a.id, f"어린이{n}") for n in range(3)]
    for book_id in (base, *children):
        await add_audience(session, library_a.id, book_id)
    await load(session, library_a.id, {"일반서": 0.99, "어린이0": 0.5, "어린이1": 0.7})
    assert (await similar(session, library_a.id, base))[0] == general
    found = await similar(session, library_a.id, base, within=children_book_ids(library_a.id))
    assert general not in found and set(found) == set(children)
    history = await find_from_history(
        session,
        MODEL,
        library_id=library_a.id,
        library_book_ids=[base],
        within=children_book_ids(library_a.id),
    )
    assert {item.library_book_id for item in history} == set(children)


async def test_unrecommendable_book_is_left_out(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 비슷한 책 추천의 범위 / 추천할 수 없는 책"""
    writer = "한작가 저"
    base = await linked(session, library_a.id, "기준", author=writer, series_keys=["묶음"])
    lost = await linked(
        session, library_a.id, "잃은책", "lost", author=writer, series_keys=["묶음"]
    )
    kept = await linked(session, library_a.id, "남은책", author=writer)
    await load(session, library_a.id, {"잃은책": 0.99, "남은책": 0.3})
    assert await similar(session, library_a.id, base) == [kept]
    assert lost not in await similar(session, library_a.id, base)


async def test_base_of_another_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/related-recommendation] 비슷한 책 추천의 범위 / 다른 기관의 기준 책"""
    theirs = await unlinked(session, library_b.id, "기준 남의책")
    await unlinked(session, library_b.id, "남의이웃")
    with pytest.raises(NotFoundError) as error:
        await find_similar(session, MODEL, library_id=library_a.id, library_book_id=theirs)
    assert "남의" not in str(error.value)
    for ranking in (series_ranking, kdc_ranking):
        with pytest.raises(NotFoundError):
            await ranking(session, library_a.id, theirs)


async def test_same_input_same_result(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 비슷한 책 같은 입력 같은 결과 / 두 번 실행"""
    ids = await _mixed_signals(session, library_a.id)
    settings = SimilarSettings(series_cap=1, mmr_lambda=0.7)
    runs = [
        await find_similar(
            session, MODEL, library_id=library_a.id, library_book_id=ids["base"], settings=settings
        )
        for _ in range(2)
    ]
    assert runs[0] == runs[1] and runs[0]
    histories = [
        await find_from_history(
            session, MODEL, library_id=library_a.id, library_book_ids=[ids["base"], ids["far"]]
        )
        for _ in range(2)
    ]
    assert histories[0] == histories[1] and histories[0]
