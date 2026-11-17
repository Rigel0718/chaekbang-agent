"""[catalog/related-recommendation] 대출 신호(`add-loan-signals`): 함께 대출, KDC 단위·순서,

최근 기록 신호, 정보나루 인기로 채우기, 빈 기록. 가짜 인코더와 가짜 대출 신호로 본다.
"""

from collections.abc import Mapping, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.central.external.data4library.definitions import AGE_CHILDREN
from app.features.children.service import children_book_ids
from app.library.recommendation.related import (
    AUTHOR,
    CO_LOAN,
    KDC,
    NATIONAL_POPULAR,
    VECTOR,
    HistorySettings,
    SimilarSettings,
    co_loan_ranking,
    find_from_history,
    find_similar,
    held_ranking,
    kdc_ranking,
)
from tests.conftest import Tenant
from tests.helpers import add_audience, add_held_book, make_isbn
from tests.library.test_related_recommendation import MODEL, _loaned, linked, load, unlinked


class FakeLoanSignals:
    def __init__(
        self,
        co_loans: Mapping[str, Sequence[str]] | None = None,
        popular: Mapping[str, Sequence[str]] | None = None,
    ) -> None:
        self._co_loans = co_loans or {}
        self._popular = popular or {}
        self.popular_asked: list[str] = []

    async def co_loans(self, isbn: str, kind: str = CO_LOAN) -> Sequence[str]:
        return self._co_loans.get(isbn, ()) if kind == CO_LOAN else ()

    async def popular(self, age_group: str) -> Sequence[str]:
        self.popular_asked.append(age_group)
        return self._popular.get(age_group, ())


async def _with_isbn(session: AsyncSession, library_id: int, title: str, n: int) -> int:
    return await unlinked(session, library_id, title, isbn=make_isbn(900 + n))


# --- 함께 대출 ---


async def test_co_loans_held_in_order(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 함께 대출 신호 / 가진 책만 순서대로"""
    base = await _with_isbn(session, library_a.id, "기준", 1)
    z = (
        await add_held_book(session, library_a.id, title="제트", isbn=make_isbn(903), official={})
    )["id"]
    x = await _with_isbn(session, library_a.id, "엑스", 4)
    signals = FakeLoanSignals({make_isbn(901): [make_isbn(904), make_isbn(902), make_isbn(903)]})
    assert await co_loan_ranking(session, library_a.id, base, signals) == [x, z]


async def test_co_loans_of_other_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/related-recommendation] 함께 대출 신호 / 다른 기관의 책"""
    base = await _with_isbn(session, library_a.id, "기준", 5)
    await _with_isbn(session, library_b.id, "와이", 6)
    signals = FakeLoanSignals({make_isbn(905): [make_isbn(906)]})
    assert await co_loan_ranking(session, library_a.id, base, signals) == []
    assert await held_ranking(session, library_a.id, [make_isbn(906)]) == []


async def test_co_loans_base_without_isbn(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 함께 대출 신호 / ISBN 없는 기준 책"""
    base = await unlinked(session, library_a.id, "기준")
    await _with_isbn(session, library_a.id, "엑스", 7)
    signals = FakeLoanSignals({"": [make_isbn(907)]})
    assert await co_loan_ranking(session, library_a.id, base, signals) == []
    assert await co_loan_ranking(session, library_a.id, base, None) == []


async def test_co_loan_evidence(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 함께 대출 신호 / 근거"""
    base = await _with_isbn(session, library_a.id, "기준", 8)
    n1 = await _with_isbn(session, library_a.id, "하나", 9)
    n2 = await _with_isbn(session, library_a.id, "둘", 10)
    pick = await _with_isbn(session, library_a.id, "셋", 11)
    await load(session, library_a.id, {"하나": 0.9, "둘": 0.8, "셋": 0.7})
    signals = FakeLoanSignals({make_isbn(908): [make_isbn(911)]})
    found = await find_similar(
        session,
        MODEL,
        library_id=library_a.id,
        library_book_id=base,
        settings=SimilarSettings(signals={VECTOR: 1.0, CO_LOAN: 1.0}),
        loan_signals=signals,
    )
    ranks = {item.library_book_id: dict(item.ranks) for item in found}
    assert ranks[pick] == {CO_LOAN: 1, VECTOR: 3}
    assert found[0].library_book_id == pick
    assert {n1, n2} <= set(ranks)


# --- KDC 단위·순서 ---


async def test_kdc_three_digits(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 같은 KDC 세목 신호 / 세 자리"""
    base = await unlinked(session, library_a.id, "기준", kdc="813.7")
    plain = await unlinked(session, library_a.id, "가", kdc="813")
    near = await unlinked(session, library_a.id, "나", kdc="813.6")
    await unlinked(session, library_a.id, "다", kdc="814")
    assert await kdc_ranking(session, library_a.id, base, level="three") == [plain, near]
    assert await kdc_ranking(session, library_a.id, base) == []


async def test_kdc_nested(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 같은 KDC 세목 신호 / 계층"""
    base = await unlinked(session, library_a.id, "기준", kdc="813.7")
    a = await unlinked(session, library_a.id, "가", kdc="813.6")
    b = await unlinked(session, library_a.id, "나", kdc="813.72")
    assert await kdc_ranking(session, library_a.id, base, level="nested") == [b, a]
    assert await kdc_ranking(session, library_a.id, base, level="nested", depth=1) == [b]


async def test_kdc_vector_order(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 같은 KDC 세목 신호 / 벡터 순서"""
    base = await unlinked(session, library_a.id, "기준", kdc="813.7")
    c = await unlinked(session, library_a.id, "가씨", kdc="813.7")
    d = await unlinked(session, library_a.id, "하디", kdc="813.7")
    await unlinked(session, library_a.id, "나가까운다른분야", kdc="325")
    await load(session, library_a.id, {"가씨": 0.2, "하디": 0.9, "나가까운다른분야": 0.99})
    assert await kdc_ranking(session, library_a.id, base) == [c, d]
    ordered = await kdc_ranking(session, library_a.id, base, order="vector", model_name=MODEL)
    assert ordered == [d, c]


async def test_kdc_settings_in_similar(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 같은 KDC 세목 신호 (설정이 비슷한 책 순위에 쓰인다)"""
    base = await unlinked(session, library_a.id, "기준", kdc="813.7")
    plain = await unlinked(session, library_a.id, "가", kdc="813")
    await load(session, library_a.id, {"가": 0.1})
    default = await find_similar(session, MODEL, library_id=library_a.id, library_book_id=base)
    assert KDC not in dict(next(i for i in default if i.library_book_id == plain).ranks)
    wide = await find_similar(
        session,
        MODEL,
        library_id=library_a.id,
        library_book_id=base,
        settings=SimilarSettings(kdc_level="three"),
    )
    assert dict(next(i for i in wide if i.library_book_id == plain).ranks)[KDC] == 1


# --- 최근 기록 신호 ---


async def test_history_kdc_signal(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 최근 기록 합치기 / 기록 신호"""
    a = await unlinked(session, library_a.id, "기준에이", kdc="813.7")
    b = await unlinked(session, library_a.id, "기준비", kdc="813.7")
    near = [await unlinked(session, library_a.id, f"이웃{n}", kdc="325") for n in range(3)]
    w = await unlinked(session, library_a.id, "먼책", kdc="813.7")
    await load(session, library_a.id, {"이웃0": 0.95, "이웃1": 0.9, "이웃2": 0.85, "먼책": 0.1})
    plain = HistorySettings(depth=3, popular_fill=False)
    base = await find_from_history(
        session, MODEL, library_id=library_a.id, library_book_ids=[a, b], settings=plain
    )
    assert [item.library_book_id for item in base] == near
    signals = HistorySettings(depth=3, popular_fill=False, signals={VECTOR: 1.0, KDC: 1.0})
    found = await find_from_history(
        session, MODEL, library_id=library_a.id, library_book_ids=[a, b], settings=signals
    )
    ranks = {item.library_book_id: dict(item.ranks) for item in found}
    assert ranks[w] == {KDC: 1}


async def test_history_author_signal(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 최근 기록 합치기 (겹치는 저자는 겹치는 수가 많은 순)"""
    a = await linked(session, library_a.id, "기준에이", author="김작가, 이작가 글")
    b = await linked(session, library_a.id, "기준비", author="김작가 글")
    one = await linked(session, library_a.id, "하나만", author="이작가 글")
    both = await linked(session, library_a.id, "둘다", author="김작가, 이작가 글")
    await load(session, library_a.id, {"하나만": 0.9, "둘다": 0.1})
    settings = HistorySettings(popular_fill=False, signals={AUTHOR: 1.0})
    found = await find_from_history(
        session, MODEL, library_id=library_a.id, library_book_ids=[a, b], settings=settings
    )
    assert [item.library_book_id for item in found][:2] == [both, one]


async def test_history_co_loan_signal(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 최근 기록 합치기 (함께 대출: 기록 책마다 RRF)"""
    a = await _with_isbn(session, library_a.id, "기준에이", 21)
    b = await _with_isbn(session, library_a.id, "기준비", 22)
    x = await _with_isbn(session, library_a.id, "엑스", 23)
    y = await _with_isbn(session, library_a.id, "와이", 24)
    signals = FakeLoanSignals(
        {make_isbn(921): [make_isbn(924), make_isbn(923)], make_isbn(922): [make_isbn(923)]}
    )
    settings = HistorySettings(popular_fill=False, signals={CO_LOAN: 1.0})
    found = await find_from_history(
        session,
        MODEL,
        library_id=library_a.id,
        library_book_ids=[a, b],
        settings=settings,
        loan_signals=signals,
    )
    assert [item.library_book_id for item in found] == [x, y]


async def test_history_signals_off(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 최근 기록 합치기 / 기록 신호 끔"""
    a = await unlinked(session, library_a.id, "기준", kdc="813.7")
    near = await unlinked(session, library_a.id, "이웃", kdc="325")
    far = await unlinked(session, library_a.id, "먼책", kdc="813.7")
    await load(session, library_a.id, {"이웃": 0.9, "먼책": 0.1})
    found = await find_from_history(
        session,
        MODEL,
        library_id=library_a.id,
        library_book_ids=[a],
        settings=HistorySettings(popular_fill=False),
    )
    assert [item.library_book_id for item in found] == [near, far]
    assert all(set(item.ranks) == {VECTOR} for item in found)


# --- 정보나루 인기로 채우기, 빈 기록 ---


async def test_fill_order(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 정보나루 인기로 채우기 / 채우는 순서"""
    base = await unlinked(session, library_a.id, "기준")
    near = await unlinked(session, library_a.id, "이웃")
    await load(session, library_a.id, {"이웃": 0.9})
    ours = [await _loaned(session, library_a.id, f"우리{n}", [1] * (3 - n)) for n in range(2)]
    nationals = [await _with_isbn(session, library_a.id, f"전국{n}", 30 + n) for n in range(3)]
    signals = FakeLoanSignals(popular={"all": [make_isbn(930 + n) for n in range(3)]})
    found = await find_from_history(
        session,
        MODEL,
        library_id=library_a.id,
        library_book_ids=[base],
        settings=HistorySettings(depth=1),
        loan_signals=signals,
    )
    assert [item.library_book_id for item in found] == [near, *ours, *nationals[:2]]
    assert dict(found[3].ranks) == {NATIONAL_POPULAR: 1}
    assert dict(found[1].ranks) == {"popular": 1}


async def test_fill_children_group(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 정보나루 인기로 채우기 / 어린이 연령 묶음"""
    kid = await _with_isbn(session, library_a.id, "그림책", 40)
    await add_audience(session, library_a.id, kid)
    await _with_isbn(session, library_a.id, "어른책", 41)
    signals = FakeLoanSignals(
        popular={"children": [make_isbn(941), make_isbn(940)], "all": [make_isbn(941)]}
    )
    found = await find_from_history(
        session,
        MODEL,
        library_id=library_a.id,
        library_book_ids=[],
        within=children_book_ids(library_a.id),
        loan_signals=signals,
        popular_group=AGE_CHILDREN.key,
    )
    assert [item.library_book_id for item in found] == [kid]
    assert signals.popular_asked == [AGE_CHILDREN.key]


async def test_fill_skips_unheld(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 정보나루 인기로 채우기 / 기관이 가지지 않은 인기 책"""
    held = await _with_isbn(session, library_a.id, "가진책", 50)
    signals = FakeLoanSignals(popular={"all": [make_isbn(951), make_isbn(950)]})
    found = await find_from_history(
        session, MODEL, library_id=library_a.id, library_book_ids=[], loan_signals=signals
    )
    assert [item.library_book_id for item in found] == [held]


async def test_empty_history_national(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/related-recommendation] 빈 기록 / 대출 행 없는 기관"""
    books = [await _with_isbn(session, library_a.id, f"책{n}", 60 + n) for n in range(7)]
    signals = FakeLoanSignals(popular={"all": [make_isbn(960 + n) for n in range(7)]})
    found = await find_from_history(
        session, MODEL, library_id=library_a.id, library_book_ids=[], loan_signals=signals
    )
    assert [item.library_book_id for item in found] == books[:5]
    assert all(set(item.ranks) == {NATIONAL_POPULAR} for item in found)


async def test_empty_history_nothing(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/related-recommendation] 빈 기록 / 아무 인기도 없음"""
    await add_held_book(session, library_a.id, title="그냥 책")
    theirs = await unlinked(session, library_b.id, "남의 책")
    for books in ([], [theirs]):
        found = await find_from_history(
            session, MODEL, library_id=library_a.id, library_book_ids=books
        )
        assert found == []
