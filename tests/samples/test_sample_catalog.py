"""표본 테스트: 실제 YES24 서지로 적재, 검색, 어린이 분류, 카드, 가짜 LLM 대화를 본다.

기대값은 책 하나하나가 아니라 조건으로 쓴다. 표본을 다시 받으면 책이 바뀌기 때문이다.
"""

import re

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import ToolContext
from app.features.children.rules import is_children_category
from app.features.children.tools import SEARCH_CHILDREN_BOOKS, children_extension
from app.library.librarian import LibrarianAnswer, Recommendation, build_librarian_profiles
from app.library.models.catalog import LibraryBook
from app.library.recommendation.cards import build_cards
from app.library.recommendation.search import SEARCH_LIMIT, search_collection
from app.library.tools import DESCRIPTION_LIMIT, SEARCH_COLLECTION
from evals.librarian.catalog import BookState, Sample, SampleCatalog, real_isbn
from evals.librarian.runner import run_scenario
from evals.librarian.scenarios import SCENARIOS
from tests.agent.fakes import FakeLlm
from tests.library.librarian_helpers import search, submit

ROLE_WORDS = re.compile(r"\s*(글그림|글,\s*그림|원저|원작|기획|감수|그림|글|저|역|외)\s*$")


def _squash(text: str) -> str:
    return "".join(text.split()).casefold()


def _scenario(scenario_id: str):
    return next(s for s in SCENARIOS if s.id == scenario_id)


def _profile(catalog: SampleCatalog):
    return build_librarian_profiles((children_extension(),))[catalog.loan_mode]


# --- 적재 ---


async def test_load_counts(session: AsyncSession, sample: Sample, catalog: SampleCatalog) -> None:
    """표본 적재: 모든 책이 들어가고 상태 규칙이 고르게 적용된다."""
    assert len(catalog.states) == len(sample.books)
    count = await session.scalar(
        select(func.count()).where(LibraryBook.library_id == catalog.library_id)
    )
    assert count == len(sample.books)
    for state in BookState:
        assert catalog.with_state(state), state
    assert catalog.recommendable == set(catalog.states) - set(
        catalog.with_state(BookState.LOST_ONLY)
    )


async def test_barcodes_have_no_isbn(
    session: AsyncSession, sample: Sample, catalog: SampleCatalog
) -> None:
    """표본 적재: 978·979가 아닌 상품 바코드와 ISSN은 ISBN 없는 기관 도서다."""
    expected = sum(real_isbn(row["isbn13"]) is None for row in sample.books)
    assert len(catalog.barcode_only) == expected
    rows = await session.execute(
        select(LibraryBook.isbn, LibraryBook.book_id).where(
            LibraryBook.id.in_(catalog.barcode_only)
        )
    )
    assert all(isbn is None and book_id is None for isbn, book_id in rows)


async def test_children_from_real_categories(sample: Sample, catalog: SampleCatalog) -> None:
    """어린이 분류: 실제 분류 값이 정확히 일치하는 공식 서지만 어린이 도서다."""
    by_title = {}
    for row in sample.books:
        by_title.setdefault(row["title"], []).append(row)
    assert catalog.children
    assert catalog.children <= catalog.official
    for book_id in catalog.children:
        rows = by_title[catalog.titles[book_id]]
        assert any(is_children_category(r["category"]) for r in rows)
    toy = [r for r in sample.books if r["category"] == "국내도서-유아-토이북"]
    toy_ids = {i for i, t in catalog.titles.items() for r in toy if r["title"] == t}
    assert not toy_ids & catalog.children  # 정확히 일치만 보므로 일반 도서다


# --- 검색 ---


async def test_dinosaur_search(session: AsyncSession, catalog: SampleCatalog) -> None:
    """검색: `공룡`이 서명에 든 추천 가능한 책을 찾고, 나온 책은 모두 공룡이 들어 있다."""
    found = await search_collection(session, catalog.library_id, ["공룡"])
    ids = [c.library_book.id for c in found]
    assert ids
    assert all("공룡" in catalog.texts[i] for i in ids)
    assert set(ids) <= catalog.recommendable
    titled = {i for i in catalog.recommendable if "공룡" in _squash(catalog.titles[i])}
    if len(titled) <= SEARCH_LIMIT:
        assert titled <= set(ids)
    # 서명에 든 책이 소개에만 든 책보다 앞이다.
    in_title = [i in titled for i in ids]
    assert in_title == sorted(in_title, reverse=True)


def _first_name(author: str) -> str:
    name = author.split("/")[0]
    while True:
        stripped = ROLE_WORDS.sub("", name)
        if stripped == name:
            return name.split(",")[0].strip()
        name = stripped


async def test_author_substring(
    session: AsyncSession, sample: Sample, catalog: SampleCatalog
) -> None:
    """검색: 실제 저자 표기(`글/그림/감수`, `글그림`, 역할 없음)의 첫 이름으로 그 책을 찾는다."""
    by_title = {row["title"]: row for row in sample.books}
    checked = 0
    for book_id in sorted(catalog.recommendable):
        name = _first_name(by_title[catalog.titles[book_id]]["author"])
        matches = [i for i in catalog.recommendable if _squash(name) in _squash(catalog.texts[i])]
        if len(_squash(name)) < 2 or len(matches) > SEARCH_LIMIT:
            continue
        found = await search_collection(session, catalog.library_id, [name])
        assert book_id in [c.library_book.id for c in found], (name, catalog.titles[book_id])
        checked += 1
    assert checked >= len(catalog.recommendable) // 2


async def test_children_tool_returns_children_only(
    session: AsyncSession, catalog: SampleCatalog
) -> None:
    """어린이 tool: 실제 분류로 정한 어린이 도서만 나온다."""
    ctx = ToolContext(catalog.library_id, session)
    data = SEARCH_CHILDREN_BOOKS.input_model(keywords=[])
    rows = await SEARCH_CHILDREN_BOOKS.handler(ctx, data)
    assert rows
    assert {r["library_book_id"] for r in rows} <= catalog.children & catalog.recommendable


async def test_description_cut_in_tool(session: AsyncSession, catalog: SampleCatalog) -> None:
    """tool 결과: 실제 소개는 200자로 잘리고 소개를 지운 책은 비어 있다."""
    ctx = ToolContext(catalog.library_id, session)
    rows = await SEARCH_COLLECTION.handler(
        ctx, SEARCH_COLLECTION.input_model(keywords=["공룡", "그림책", "요리", "소설"])
    )
    descriptions = [r["description"] for r in rows if r["description"]]
    assert descriptions
    assert all(len(d) <= DESCRIPTION_LIMIT + 1 for d in descriptions)
    assert any(d.endswith("…") for d in descriptions)


# --- 카드 ---


async def test_cards_from_db(session: AsyncSession, catalog: SampleCatalog) -> None:
    """카드: 서명은 DB 값이고 공식 서지가 있으면 YES24 표지 출처와 링크가 있다."""
    ids = sorted(catalog.recommendable)[:5]
    answer = LibrarianAnswer(
        message="추천",
        recommendations=[Recommendation(library_book_id=i, reason="지어낸 서명") for i in ids],
        suggest_book_request=False,
    )
    cards = await build_cards(session, catalog.library_id, answer)
    assert [c.library_book_id for c in cards] == ids
    for card in cards:
        assert card.title == catalog.titles[card.library_book_id]
        on_loan = catalog.states[card.library_book_id] == BookState.ON_LOAN
        assert (card.available_count, card.on_loan_count) == ((0, 1) if on_loan else (1, 0))
        if card.library_book_id in catalog.official:
            assert card.cover_source == "YES24"
            assert card.product_url and card.product_url.startswith("https://www.yes24.com/")
        else:
            assert card.cover_source is None


# --- 가짜 LLM 대화 흐름 ---


async def test_dinosaur_conversation(session: AsyncSession, catalog: SampleCatalog) -> None:
    """대화: 공룡 시나리오를 가짜 LLM으로 돌리면 규칙 위반이 없고 기대가 맞는다."""
    found = await search_collection(session, catalog.library_id, ["공룡"])
    ids = [c.library_book.id for c in found][:3]
    llm = FakeLlm([search("공룡"), submit("공룡 책이에요", *ids)])
    result = await run_scenario(session, llm, _profile(catalog), catalog, _scenario("dinosaur"))
    assert result.violations == {}
    assert result.expectation_met
    assert result.last.tools == ("search_collection",)


async def test_children_conversation_blocks_general(
    session: AsyncSession, catalog: SampleCatalog
) -> None:
    """대화: 어린이 요청에 일반 도서를 내면 검사가 막고, 나간 카드에는 어린이 도서만 있다."""
    general = sorted(catalog.recommendable - catalog.children)[0]
    kids = sorted(catalog.recommendable & catalog.children)[0]
    llm = FakeLlm([submit("둘 다요", general, kids), submit("이 책요", kids)])
    result = await run_scenario(
        session, llm, _profile(catalog), catalog, _scenario("child-dinosaur")
    )
    assert result.children_judged
    assert result.violations == {}
    assert [c["library_book_id"] for c in result.last.answer["recommendations"]] == [kids]


async def test_lost_book_never_shown(session: AsyncSession, catalog: SampleCatalog) -> None:
    """대화: 분실 사본만 있는 책은 재시도 한도까지 내도 카드에 나오지 않는다."""
    lost = catalog.with_state(BookState.LOST_ONLY)[0]
    bad = submit("이 책요", lost)
    result = await run_scenario(
        session, FakeLlm([bad, bad, bad]), _profile(catalog), catalog, _scenario("history")
    )
    assert result.last.answer["recommendations"] == []
    assert result.last.status == "fallback"
    assert result.violations == {}
