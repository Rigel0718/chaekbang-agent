"""[agent/librarian] AI 사서 프로필, 조회 tool, 최종 답, 소장 검사, 카드. 가짜 LLM만 쓴다."""

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.llm import ToolResult
from app.agent.models import RunStatus
from app.library.librarian import (
    FALLBACK_ANSWER,
    REPAIRED_MESSAGE,
    LibrarianAnswer,
    Recommendation,
    build_librarian_profiles,
)
from app.library.models.library import LoanMode
from app.library.recommendation.cards import build_cards
from app.library.tools import NO_DESCRIPTION
from tests.agent.fakes import FakeLlm, answers, done
from tests.conftest import Tenant
from tests.helpers import add_member
from tests.library.librarian_helpers import (
    add_held_book,
    call,
    detail,
    librarian,
    run_librarian,
    search,
    submit,
    turn,
)


def _tool_results(llm: FakeLlm, request: int) -> list[ToolResult]:
    return [m for m in llm.requests[request]["messages"] if isinstance(m, ToolResult)]


def _answer(*book_ids: int, reason: str = "좋아요") -> LibrarianAnswer:
    return LibrarianAnswer(
        message="추천해요",
        recommendations=[Recommendation(library_book_id=i, reason=reason) for i in book_ids],
        suggest_book_request=False,
    )


# --- 조회 tool ---


async def test_profile_tools(session: AsyncSession) -> None:
    """[agent/librarian] 조회 tool / 프로필의 tool"""
    for prof in build_librarian_profiles().values():
        assert [t.name for t in prof.tools] == ["search_collection", "find_book", "get_book_detail"]
        assert prof.answer_tool.name == "submit_answer"


async def test_search_tool_result(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/librarian] 조회 tool / 검색 결과의 소개는 200자로 자른다"""
    book = await add_held_book(session, library_a.id, title="공룡 백과", description="가" * 500)
    llm = FakeLlm([search("공룡"), submit("추천해요", book["id"])])
    await run_librarian(session, llm, library_a.id)
    [result] = _tool_results(llm, 1)
    assert not result.is_error
    assert f'"library_book_id": {book["id"]}' in result.content
    assert "가" * 200 + "…" in result.content
    assert "가" * 201 not in result.content


async def test_detail_without_description(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/librarian] 조회 tool / 소개 없는 책"""
    book = await add_held_book(session, library_a.id, title="공룡 백과")
    llm = FakeLlm([detail(book["id"]), submit("소개 정보가 없어요.")])
    await run_librarian(session, llm, library_a.id, "공룡 백과는 무슨 내용이에요?")
    [result] = _tool_results(llm, 1)
    assert not result.is_error
    assert NO_DESCRIPTION in result.content


async def test_detail_other_library(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[agent/librarian] 조회 tool / 다른 기관 도서 상세"""
    theirs = await add_held_book(session, library_b.id, title="공룡 백과", description="비밀 소개")
    llm = FakeLlm([detail(theirs["id"]), submit("찾지 못했어요.")])
    await run_librarian(session, llm, library_a.id)
    [result] = _tool_results(llm, 1)
    assert result.is_error
    assert "찾을 수 없습니다" in result.content
    assert "비밀 소개" not in result.content


async def test_find_book_tool_typo(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[agent/librarian] 조회 tool / 서명·저자 찾기 tool의 오타"""
    book = await add_held_book(session, library_a.id, title="데미안", author="헤르만 헤세")
    await add_held_book(session, library_b.id, title="데미안 B")
    llm = FakeLlm([turn(call("find_book", {"query": "데미얀"})), submit("있어요", book["id"])])
    await run_librarian(session, llm, library_a.id, "데미얀 있어요?")
    [result] = _tool_results(llm, 1)
    assert not result.is_error
    assert f'"library_book_id": {book["id"]}' in result.content
    assert "데미안 B" not in result.content


async def test_find_book_tool_without_children(session: AsyncSession) -> None:
    """어린이 기능 없이 만든 프로필에도 서명·저자 찾기 tool이 있다."""
    for prof in build_librarian_profiles(()).values():
        assert "find_book" in [t.name for t in prof.tools]


# --- 최종 답 ---


async def test_message_too_long(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/librarian] 최종 답 / 길이 초과"""
    book = await add_held_book(session, library_a.id, title="공룡 백과")
    llm = FakeLlm([submit("가" * 301, book["id"]), submit("짧게", book["id"])])
    events = await run_librarian(session, llm, library_a.id)
    [result] = _tool_results(llm, 1)
    assert result.is_error
    assert "message" in result.content
    [answer] = answers(events)
    assert answer.message == "짧게"


async def test_reason_and_count_limits(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/librarian] 최종 답 / 이유 120자, 추천 5권 상한"""
    book = await add_held_book(session, library_a.id, title="공룡 백과")
    llm = FakeLlm(
        [
            submit("추천", book["id"], reason="가" * 121),
            submit("추천", *([book["id"]] * 6)),
            submit("추천", book["id"]),
        ]
    )
    events = await run_librarian(session, llm, library_a.id)
    assert _tool_results(llm, 1)[-1].is_error
    assert _tool_results(llm, 2)[-1].is_error
    assert done(events).status == RunStatus.COMPLETED


async def test_duplicate_book_one_card(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/librarian] 최종 답 / 같은 책 중복"""
    book = await add_held_book(session, library_a.id, title="공룡 백과")
    other = await add_held_book(session, library_a.id, title="공룡 도감")
    cards = await build_cards(session, library_a.id, _answer(book["id"], other["id"], book["id"]))
    assert [c.library_book_id for c in cards] == [book["id"], other["id"]]


# --- 소장 검사 ---


async def test_other_library_book_rejected(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[agent/librarian] 소장 검사 / 다른 기관의 책"""
    ours = await add_held_book(session, library_a.id, title="공룡 백과")
    theirs = await add_held_book(session, library_b.id, title="공룡 도감")
    llm = FakeLlm([submit("둘 다요", ours["id"], theirs["id"]), submit("이 책요", ours["id"])])
    events = await run_librarian(session, llm, library_a.id)
    [result] = _tool_results(llm, 1)
    assert result.is_error
    assert str(theirs["id"]) in result.content
    [answer] = answers(events)
    assert [r.library_book_id for r in answer.recommendations] == [ours["id"]]


async def test_lost_only_rejected(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/librarian] 소장 검사 / 분실 사본만 있는 책"""
    lost = await add_held_book(session, library_a.id, "lost", "damaged", title="공룡 백과")
    llm = FakeLlm([submit("이 책요", lost["id"]), submit("없어요", suggest=True)])
    events = await run_librarian(session, llm, library_a.id)
    assert _tool_results(llm, 1)[-1].is_error
    [answer] = answers(events)
    assert answer.recommendations == []


async def test_repaired_answer_message(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/librarian] 소장 검사 / 정리한 답의 문장"""
    ours = await add_held_book(session, library_a.id, title="공룡 백과")
    lost = await add_held_book(session, library_a.id, "lost", title="공룡 도감")
    bad = submit("공룡 도감도 꼭 보세요", ours["id"], lost["id"])
    llm = FakeLlm([bad, bad, bad])
    events = await run_librarian(session, llm, library_a.id)
    [answer] = answers(events)
    assert done(events).status == RunStatus.REPAIRED
    assert answer.message == REPAIRED_MESSAGE
    assert [r.library_book_id for r in answer.recommendations] == [ours["id"]]
    cards = await build_cards(session, library_a.id, answer)
    assert [c.library_book_id for c in cards] == [ours["id"]]


async def test_nothing_left_fallback(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/librarian] 소장 검사 / 남는 책 없음"""
    lost = await add_held_book(session, library_a.id, "lost", title="공룡 도감")
    bad = submit("공룡 도감요", lost["id"])
    events = await run_librarian(session, FakeLlm([bad, bad, bad]), library_a.id)
    assert answers(events) == [FALLBACK_ANSWER]
    assert done(events).status == RunStatus.FALLBACK


# --- 추천 카드 ---


async def test_card_uses_db_values(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/librarian] 추천 카드 / 서지는 DB 값"""
    book = await add_held_book(
        session,
        library_a.id,
        title="기관 서명",
        official={"title": "공식 서명", "author": "공식 저자", "publisher": "공식 출판사"},
        holding={"shelf_location": "어린이 서가", "call_number": "457-ㄱ123"},
    )
    [card] = await build_cards(session, library_a.id, _answer(book["id"], reason="『지어낸 책』"))
    assert (card.title, card.author, card.publisher) == ("공식 서명", "공식 저자", "공식 출판사")
    assert card.reason == "『지어낸 책』"
    assert (card.shelf_location, card.call_number) == ("어린이 서가", "457-ㄱ123")
    assert (card.available_count, card.on_loan_count) == (1, 0)


async def test_card_on_loan(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/librarian] 추천 카드 / 대출 중 표시"""
    book = await add_held_book(session, library_a.id, "on_loan", "on_loan", "lost", title="공룡")
    [card] = await build_cards(session, library_a.id, _answer(book["id"]))
    assert (card.available_count, card.on_loan_count) == (0, 2)


async def test_card_cover_source(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/librarian] 추천 카드 / 표지 출처"""
    book = await add_held_book(
        session,
        library_a.id,
        title="공룡",
        official={
            "cover_url": "https://image.yes24.com/goods/1/L",
            "external_source": "yes24",
            "external_url": "https://www.yes24.com/product/goods/1",
        },
    )
    [card] = await build_cards(session, library_a.id, _answer(book["id"]))
    assert card.cover_url == "https://image.yes24.com/goods/1/L"
    assert card.cover_source == "YES24"
    assert card.product_url == "https://www.yes24.com/product/goods/1"


async def test_card_other_library_dropped(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[agent/librarian] 추천 카드 / 다른 기관의 책은 카드가 되지 않음"""
    theirs = await add_held_book(session, library_b.id, title="공룡")
    assert await build_cards(session, library_a.id, _answer(theirs["id"])) == []


# --- 운영 방식별 안내 ---


async def test_imported_card_synced_at(session: AsyncSession, library_b: Tenant) -> None:
    """[agent/librarian] 운영 방식별 안내 / 가져오기 기관의 카드"""
    synced = (await session.execute(text("SELECT now() - interval '2 days'"))).scalar_one()
    book = await add_held_book(
        session, library_b.id, title="공룡", holding={"last_synced_at": synced}
    )
    [card] = await build_cards(session, library_b.id, _answer(book["id"]))
    assert card.status_synced_at == synced


async def test_prompt_by_loan_mode(
    session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[agent/librarian] 운영 방식별 안내 / 운영 방식별 프로필"""
    systems = {}
    for tenant, mode in ((library_a, LoanMode.INTERNAL), (library_b, LoanMode.IMPORTED)):
        llm = FakeLlm([submit("없어요", suggest=True)])
        await run_librarian(session, llm, tenant.id, prof=librarian(mode))
        systems[mode] = llm.requests[0]["system"]
    assert systems[LoanMode.INTERNAL] != systems[LoanMode.IMPORTED]
    assert "가져와" in systems[LoanMode.IMPORTED]
    assert "가져와" not in systems[LoanMode.INTERNAL]


# --- 쓰기 tool 없음 ---


async def _snapshot(session: AsyncSession) -> list:
    rows = []
    for table in ("holdings", "loans", "members"):
        result = await session.execute(text(f"SELECT * FROM {table} ORDER BY id"))
        rows.append([tuple(r) for r in result])
    return rows


async def test_no_writes(session: AsyncSession, library_a: Tenant) -> None:
    """[agent/librarian] 쓰기 tool 없음 / 대화 후 데이터 변화 없음"""
    book = await add_held_book(session, library_a.id, title="공룡 백과")
    await add_member(session, library_a.id, "M0001")
    before = await _snapshot(session)
    llm = FakeLlm([search("공룡"), detail(book["id"]), submit("이 책 빌려 갈게요", book["id"])])
    await run_librarian(session, llm, library_a.id, "공룡 백과 대출해 줘. 회원번호 M0001")
    assert await _snapshot(session) == before
    names = {t.name for p in build_librarian_profiles().values() for t in p.tools}
    assert names == {"search_collection", "find_book", "get_book_detail"}  # 모두 조회
    count = await session.scalar(select(func.count()).select_from(text("loans")))
    assert count == 0


async def test_search_tool_official_without_subtitle(
    session: AsyncSession, library_a: Tenant
) -> None:
    """[agent/librarian] 조회 tool / 부제·시리즈 없는 공식 서지 (표본 테스트에서 찾은 오류)"""
    book = await add_held_book(session, library_a.id, title="공룡 백과", official={})
    llm = FakeLlm([search("공룡"), detail(book["id"]), submit("추천해요", book["id"])])
    await run_librarian(session, llm, library_a.id)
    results = _tool_results(llm, 2)
    assert [r.is_error for r in results] == [False, False]
    assert '"subtitle": null' in results[0].content
