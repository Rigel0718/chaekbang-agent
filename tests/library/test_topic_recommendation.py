"""[catalog/topic-recommendation] 주제로 찾기: 깊은 키워드 순위, 범위, 같은 입력 같은 결과.

가짜 인코더로 돈다. 순위 합치기·시리즈 묶기·다양화의 계산은 `test_ranking.py`가 본다.
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.central.official_embeddings import run_official_embedding
from app.features.children.service import children_book_ids
from app.library.recommendation.embeddings import run_library_embedding
from app.library.recommendation.search import search_collection
from app.library.recommendation.topic import TopicSettings, find_by_topic, keyword_ranking
from tests.conftest import Tenant
from tests.embedding_helpers import FakeEmbedder, toward, unit
from tests.helpers import add_audience, add_held_book


async def _load(session: AsyncSession, embedder: FakeEmbedder, library_id: int) -> None:
    await run_official_embedding(session, embedder, full=True)
    await run_library_embedding(session, embedder, full=True, library_id=library_id)


def _embedder(cosines: dict[str, float]) -> FakeEmbedder:
    """서명에 든 낱말마다 질의 벡터(`질의`)와의 유사도를 정한다."""
    return FakeEmbedder(
        vectors={"질의": unit(1), **{word: toward(c) for word, c in cosines.items()}}
    )


async def _find(session: AsyncSession, embedder, library_id: int, **options):
    options.setdefault("text", "질의")
    options.setdefault("keywords", ["공룡"])
    found = await find_by_topic(session, embedder, library_id=library_id, **options)
    return [item.library_book_id for item in found]


async def test_keyword_ranking_goes_deeper_than_search(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/topic-recommendation] 깊은 키워드 순위 / 상한보다 깊게"""
    for i in range(30):
        # 서명·소개에 맞는 위치를 섞어 점수가 여러 가지가 되게 한다
        values = {"title": f"공룡 이야기 {i:02d}"} if i % 3 else {"description": "공룡이 나온다"}
        values.setdefault("title", f"옛날 이야기 {i:02d}")
        await add_held_book(
            session, library_a.id, "on_loan" if i % 4 == 0 else "available", **values
        )
    await add_held_book(session, library_a.id, title="고래 이야기")
    ranking = await keyword_ranking(session, library_a.id, ["공룡"], depth=30)
    assert len(ranking) == 30 and len(set(ranking)) == 30
    searched = await search_collection(session, library_a.id, ["공룡"])
    assert ranking[:10] == [c.library_book.id for c in searched]


async def test_keyword_ranking_only_matching_books(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[catalog/topic-recommendation] 깊은 키워드 순위 / 맞지 않는 책"""
    ids = [(await add_held_book(session, library_a.id, title=f"공룡 {i}"))["id"] for i in range(3)]
    for i in range(5):
        await add_held_book(session, library_a.id, title=f"고래 {i}")
    assert sorted(await keyword_ranking(session, library_a.id, ["공룡"], depth=30)) == ids
    assert await keyword_ranking(session, library_a.id, [], depth=30) == []
    assert await keyword_ranking(session, library_a.id, ["  "], depth=30) == []


async def test_children_condition_comes_first(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/topic-recommendation] 주제로 찾기의 범위 / 어린이 조건"""
    # 서명과 소개 모두 맞아 키워드 점수가 가장 높고, 벡터도 가장 가깝다
    general = await add_held_book(
        session, library_a.id, title="공룡 대백과 일반서", description="공룡 일반서"
    )
    children = []
    for word in ("어린이하나", "어린이둘", "어린이셋"):
        book = await add_held_book(session, library_a.id, title=f"공룡 {word}")
        await add_audience(session, library_a.id, book["id"])
        children.append(book["id"])
    quiet = await add_held_book(session, library_a.id, title="조용한 그림책 어린이넷")
    await add_audience(session, library_a.id, quiet["id"])
    embedder = _embedder(
        {"일반서": 0.99, "어린이하나": 0.5, "어린이둘": 0.7, "어린이셋": 0.6, "어린이넷": 0.9}
    )
    await _load(session, embedder, library_a.id)

    assert (await _find(session, embedder, library_a.id))[0] == general["id"]
    found = await _find(session, embedder, library_a.id, within=children_book_ids(library_a.id))
    assert general["id"] not in found
    assert set(found) == {*children, quiet["id"]}


async def test_unrecommendable_book_is_left_out(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/topic-recommendation] 주제로 찾기의 범위 / 추천할 수 없는 책"""
    lost = await add_held_book(session, library_a.id, "lost", title="공룡 공룡 잃은책")
    kept = await add_held_book(session, library_a.id, title="공룡 남은책")
    embedder = _embedder({"잃은책": 0.99, "남은책": 0.3})
    await _load(session, embedder, library_a.id)
    found = await _find(session, embedder, library_a.id)
    assert found == [kept["id"]]
    assert lost["id"] not in found


async def test_other_library_book_is_left_out(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/topic-recommendation] 주제로 찾기의 범위 / 다른 기관의 책"""
    mine = await add_held_book(session, library_a.id, title="공룡 우리책")
    theirs = await add_held_book(session, library_b.id, title="공룡 공룡 남의책")
    embedder = _embedder({"우리책": 0.2, "남의책": 0.99})
    await _load(session, embedder, library_a.id)
    await _load(session, embedder, library_b.id)
    found = await _find(session, embedder, library_a.id)
    assert found == [mine["id"]]
    assert theirs["id"] not in found


async def test_same_input_same_result(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/topic-recommendation] 같은 입력 같은 결과 / 두 번 실행"""
    series = {"series_keys": ["공룡탐험대"], "series_name": "공룡 탐험대"}
    for i in range(4):
        await add_held_book(
            session,
            library_a.id,
            title=f"공룡 탐험 {i}",
            official={"title": f"공룡 탐험 {i}", **series},
        )
    for i in range(6):
        await add_held_book(session, library_a.id, title=f"바다 생물 {i}", description="공룡 시대")
    embedder = FakeEmbedder()
    await _load(session, embedder, library_a.id)
    settings = TopicSettings(series_cap=1, mmr_lambda=0.5, limit=5)
    runs = [
        await find_by_topic(
            session,
            embedder,
            library_id=library_a.id,
            text="공룡이 나오는 책",
            keywords=["공룡"],
            settings=settings,
        )
        for _ in range(2)
    ]
    assert runs[0] == runs[1]
    assert len(runs[0]) == 5
    # 같은 시리즈 네 권 중 한 권만 남고 빠진 권수가 적힌다
    assert sum(item.series_hidden for item in runs[0]) == 3


async def test_signals_can_be_turned_off(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/topic-recommendation] 순위 합치기 / 신호 가중치 (주제로 찾기에서)

    벡터 가중치가 0이면 인코더를 부르지 않고, 낱말 입력이면 낱말을 이어 질의로 쓴다.
    """
    near = await add_held_book(session, library_a.id, title="가까운책")
    word = await add_held_book(session, library_a.id, title="공룡 낱말책")
    embedder = _embedder({"가까운책": 0.9, "낱말책": 0.1})
    await _load(session, embedder, library_a.id)

    only_keyword = TopicSettings(vector_weight=0)
    assert await _find(session, embedder, library_a.id, settings=only_keyword) == [word["id"]]
    assert embedder.query_calls == []

    only_vector = TopicSettings(keyword_weight=0, vector_input="keywords")
    found = await _find(
        session,
        embedder,
        library_a.id,
        text="문장",
        keywords=["질의", "하나"],
        settings=only_vector,
    )
    assert found == [near["id"], word["id"]]
    assert embedder.query_calls == [["질의 하나"]]
