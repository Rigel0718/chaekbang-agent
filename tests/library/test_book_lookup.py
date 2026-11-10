"""[catalog/book-lookup] 서명·저자 찾기와 자동완성."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.library.recommendation import lookup
from app.library.recommendation.lookup import (
    FIND_LIMIT,
    Stage,
    find_books,
    found_in_text,
    get_findable,
    suggest_books,
)
from tests.conftest import Tenant
from tests.helpers import add_audience, add_held_book


async def _found(session: AsyncSession, library_id: int, query: str) -> list[str]:
    return [f.candidate.library_book.title for f in await find_books(session, library_id, query)]


async def _suggested(session: AsyncSession, library_id: int, query: str) -> list[str]:
    return [s.title for s in await suggest_books(session, library_id, query)]


# --- 찾을 수 있는 책 ---


async def test_other_library_book(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[catalog/book-lookup] 찾을 수 있는 책 / 다른 기관의 책"""
    await add_held_book(session, library_b.id, title="데미안")
    assert await _found(session, library_a.id, "데미안") == []
    assert await _suggested(session, library_a.id, "데미") == []
    assert await found_in_text(session, library_a.id, "데미안 있어요?") == []


async def test_lost_only_book(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 찾을 수 있는 책 / 분실 사본만 있는 책"""
    lost = await add_held_book(session, library_a.id, "lost", title="데미안")
    assert await _found(session, library_a.id, "데미안") == []
    assert await _suggested(session, library_a.id, "데미") == []
    try:
        await get_findable(session, library_a.id, lost["id"])
    except NotFoundError:
        pass
    else:
        raise AssertionError("분실 사본만 있는 책은 고를 수 없다")


async def test_children_and_general_both_found(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 찾을 수 있는 책 / 어린이 구분과 무관"""
    kids = await add_held_book(session, library_a.id, title="공룡 그림책")
    await add_audience(session, library_a.id, kids["id"])
    await add_held_book(session, library_a.id, title="공룡 진화사")
    assert sorted(await _found(session, library_a.id, "공룡")) == ["공룡 그림책", "공룡 진화사"]


# --- 서명·저자 찾기 ---


async def test_exact_title_first(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 서명·저자 찾기 / 정확한 서명"""
    await add_held_book(session, library_a.id, title="데미안 다시 읽기")
    await add_held_book(session, library_a.id, title="데미안")
    found = await find_books(session, library_a.id, "데미안")
    assert found[0].candidate.library_book.title == "데미안"
    assert found[0].stage == Stage.TITLE_EXACT


async def test_spacing_difference(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 서명·저자 찾기 / 띄어쓰기 차이"""
    await add_held_book(session, library_a.id, title="최소한의 한국사")
    assert await _found(session, library_a.id, "최소한의한국사") == ["최소한의 한국사"]


async def test_part_of_title(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 서명·저자 찾기 / 서명 일부"""
    title = "은하수를 여행하는 히치하이커를 위한 안내서 1"
    await add_held_book(session, library_a.id, title=title)
    assert await _found(session, library_a.id, "히치하이커") == [title]


async def test_author(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 서명·저자 찾기 / 저자"""
    await add_held_book(
        session, library_a.id, title="프로젝트 헤일메리", author="앤디 위어 저/박아람 역"
    )
    assert await _found(session, library_a.id, "앤디위어") == ["프로젝트 헤일메리"]


async def test_vowel_typo(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 서명·저자 찾기 / 모음 오타"""
    await add_held_book(session, library_a.id, title="데미안")
    [found] = await find_books(session, library_a.id, "데미얀")
    assert found.candidate.library_book.title == "데미안"
    assert found.stage == Stage.FUZZY


async def test_final_consonant_typo(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 서명·저자 찾기 / 받침 오타"""
    await add_held_book(session, library_a.id, title="싯다르타")
    assert await _found(session, library_a.id, "시다르타") == ["싯다르타"]


async def test_unrelated_query(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 서명·저자 찾기 / 관계없는 질의"""
    for title in ("데미안", "싯다르타", "최소한의 한국사", "공룡 그림책", "요리 노트"):
        await add_held_book(session, library_a.id, title=title)
    assert await _found(session, library_a.id, "양자회로설계") == []


async def test_limit(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 서명·저자 찾기 / 개수 제한"""
    for i in range(FIND_LIMIT + 1):
        await add_held_book(session, library_a.id, title=f"공룡 이야기 {i}")
    assert len(await _found(session, library_a.id, "공룡")) == FIND_LIMIT


async def test_special_characters_are_literal(session: AsyncSession, library_a: Tenant) -> None:
    """`%`, `_`는 글자 그대로 찾는다. 와일드카드로 맞는 책은 포함이 아니라 오타 유사로만 나온다."""
    await add_held_book(session, library_a.id, title="100% 여행")
    await add_held_book(session, library_a.id, title="1000 여행")
    found = await find_books(session, library_a.id, "100%")
    contained = [f.candidate.library_book.title for f in found if f.stage != Stage.FUZZY]
    assert contained == ["100% 여행"]


# --- 찾기 결과 순서 ---


async def test_exact_before_prefix(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 찾기 결과 순서 / 정확한 일치가 먼저"""
    await add_held_book(session, library_a.id, title="데미안 읽기")
    await add_held_book(session, library_a.id, title="데미안")
    assert await _found(session, library_a.id, "데미안") == ["데미안", "데미안 읽기"]


async def test_title_before_author(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 찾기 결과 순서 / 서명이 저자보다 먼저"""
    await add_held_book(session, library_a.id, title="여름의 책", author="헤세 연구회")
    await add_held_book(session, library_a.id, title="헤세 평전", author="김작가")
    assert await _found(session, library_a.id, "헤세") == ["헤세 평전", "여름의 책"]


async def test_contains_before_fuzzy(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 찾기 결과 순서 / 포함이 유사보다 먼저"""
    await add_held_book(session, library_a.id, title="데미얀 연구")
    await add_held_book(session, library_a.id, title="데미안")
    found = await find_books(session, library_a.id, "데미얀")
    assert [f.candidate.library_book.title for f in found] == ["데미얀 연구", "데미안"]
    assert [f.stage for f in found] == [Stage.TITLE_PREFIX, Stage.FUZZY]


async def test_available_first_in_same_stage(session: AsyncSession, library_a: Tenant) -> None:
    """같은 방식 안에서는 대출 가능한 책이 먼저다."""
    await add_held_book(session, library_a.id, "on_loan", title="공룡 가")
    await add_held_book(session, library_a.id, "available", title="공룡 나")
    assert await _found(session, library_a.id, "공룡") == ["공룡 나", "공룡 가"]


# --- 자동완성 ---


async def test_suggest_composing_jamo(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 자동완성 / 조합 중인 자모"""
    await add_held_book(session, library_a.id, title="데미안")
    assert await _suggested(session, library_a.id, "데미ㅇ") == ["데미안"]


async def test_suggest_word_prefix(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 자동완성 / 낱말 앞부분"""
    await add_held_book(session, library_a.id, title="진짜 진짜 재밌는 공룡 그림책")
    assert await _suggested(session, library_a.id, "그림ㅊ") == ["진짜 진짜 재밌는 공룡 그림책"]


async def test_suggest_author_prefix(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 자동완성 / 저자 앞부분"""
    await add_held_book(session, library_a.id, title="데미안", author="헤르만 헤세")
    assert await _suggested(session, library_a.id, "헤르ㅁ") == ["데미안"]


async def test_suggest_title_prefix_first(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 자동완성 / 서명 앞부분이 먼저"""
    await add_held_book(session, library_a.id, title="우리 동네 공룡")
    await add_held_book(session, library_a.id, title="공룡 백과")
    assert await _suggested(session, library_a.id, "공룡") == ["공룡 백과", "우리 동네 공룡"]


async def test_suggest_no_typo(session: AsyncSession, library_a: Tenant) -> None:
    """자동완성은 오타 유사를 쓰지 않는다."""
    await add_held_book(session, library_a.id, title="데미안")
    assert await _suggested(session, library_a.id, "데먀") == []


@pytest.mark.parametrize("threshold", [0.8, 0.85, 0.9])
async def test_distance_over_limit_is_not_a_match(
    session: AsyncSession, library_a: Tenant, monkeypatch: pytest.MonkeyPatch, threshold: float
) -> None:
    """편집 거리가 상한을 넘은 값("상한+1")이 문턱과 같아도 맞지 않는다(평가에서 찾은 오류)."""
    monkeypatch.setattr(lookup, "FOUND_THRESHOLD", threshold)
    await add_held_book(session, library_a.id, title="붙여도 붙여도 공룡 스티커왕")
    assert await found_in_text(session, library_a.id, "아무 책이나 추천해 주세요") == []


# --- 판본·묶음 표기 무시 ---


async def test_edition_marker_title(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 판본·묶음 표기 무시 / 판본 표기가 붙은 서명"""
    title = "진짜 진짜 재밌는 공룡 그림책 (완전판)"
    await add_held_book(session, library_a.id, title=title)
    [found] = await find_books(session, library_a.id, "진짜 진짜 재밌는 공룡 그림책")
    assert found.stage == Stage.TITLE_EXACT
    assert found.candidate.library_book.shown("title") == title  # 보이는 서명은 그대로


async def test_leading_bracket_marker(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 판본·묶음 표기 무시 / 앞에 붙은 대괄호 표기"""
    await add_held_book(session, library_a.id, title="[예스리커버] 아는 만큼 보인다")
    assert await _suggested(session, library_a.id, "아는 만큼") == ["[예스리커버] 아는 만큼 보인다"]


async def test_bundle_marker(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 판본·묶음 표기 무시 / 묶음 상품 표기"""
    await add_held_book(
        session, library_a.id, title="작고 귀엽고 사라지는 것들 (친필 사인본) + 엽서 3종"
    )
    [found] = await find_books(session, library_a.id, "작고 귀엽고 사라지는 것들")
    assert found.stage == Stage.TITLE_EXACT


async def test_unclosed_parenthesis(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 판본·묶음 표기 무시 / 닫히지 않은 괄호"""
    await add_held_book(
        session, library_a.id, title="EBS 수능특강 사회·문화 (2026년) (2027 수능대비"
    )
    [found] = await find_books(session, library_a.id, "EBS 수능특강 사회·문화")
    assert found.stage == Stage.TITLE_EXACT


async def test_marker_only_title(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 판본·묶음 표기 무시 / 표기만 있는 서명"""
    await add_held_book(session, library_a.id, title="(주)")
    assert await _found(session, library_a.id, "(주)") == ["(주)"]


async def test_plus_without_spaces(session: AsyncSession, library_a: Tenant) -> None:
    """[catalog/book-lookup] 판본·묶음 표기 무시 / 공백 없는 더하기"""
    await add_held_book(session, library_a.id, title="C++ 첫걸음")
    assert await _found(session, library_a.id, "C++") == ["C++ 첫걸음"]


async def test_query_with_marker(session: AsyncSession, library_a: Tenant) -> None:
    """질의에 판본 표기를 쳐도 같은 규칙으로 맞는다."""
    await add_held_book(session, library_a.id, title="데미안")
    [found] = await find_books(session, library_a.id, "데미안 (리커버)")
    assert found.stage == Stage.TITLE_EXACT


async def test_title_as_typed_first_among_editions(
    session: AsyncSession, library_a: Tenant
) -> None:
    """판본 표기를 지우면 같아지는 책 중에서는 원래 서명이 질의와 같은 책이 먼저다."""
    await add_held_book(session, library_a.id, title="공룡 그림책")
    await add_held_book(session, library_a.id, title="공룡 그림책 (완전판)")
    assert await _found(session, library_a.id, "공룡 그림책 (완전판)") == [
        "공룡 그림책 (완전판)",
        "공룡 그림책",
    ]
    assert await _found(session, library_a.id, "공룡 그림책") == [
        "공룡 그림책",
        "공룡 그림책 (완전판)",
    ]
