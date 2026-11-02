"""owner-ops/curation-content 스펙 테스트 (저장 계층 제약)."""

from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import VALID_ISBN, assert_rejected, insert


async def test_curation_default_status_is_draft(session: AsyncSession) -> None:
    """[owner-ops/curation-content] 추천 콘텐츠의 승인 상태 / 기본 상태"""
    row = await insert(session, "curations", kind="today_pick", title="오늘의 추천", body="...")
    assert row["status"] == "draft"


async def test_curation_rejects_unknown_status(session: AsyncSession) -> None:
    """[owner-ops/curation-content] 추천 콘텐츠의 승인 상태 / 허용되지 않은 상태"""
    await assert_rejected(
        session, "curations", kind="today_pick", title="t", body="b", status="deleted"
    )


async def test_curation_rejects_unknown_kind(session: AsyncSession) -> None:
    """[owner-ops/curation-content] 추천 콘텐츠의 승인 상태 / 허용되지 않은 종류"""
    await assert_rejected(session, "curations", kind="banner", title="t", body="b")


async def test_quote_rejects_empty_text(session: AsyncSession) -> None:
    """[owner-ops/curation-content] 사장님이 등록한 글귀 / 빈 본문"""
    await assert_rejected(session, "quotes", text="")


async def test_quote_rejects_unknown_source_book(session: AsyncSession) -> None:
    """[owner-ops/curation-content] 사장님이 등록한 글귀 / 없는 출처 도서"""
    await assert_rejected(session, "quotes", text="어른들은 숫자를 좋아한다.", isbn=VALID_ISBN)


async def test_quote_is_active_by_default(session: AsyncSession) -> None:
    """[owner-ops/curation-content] 사장님이 등록한 글귀 (사용 여부 기본값)"""
    row = await insert(session, "quotes", text="어른들은 숫자를 좋아한다.")
    assert row["is_active"] is True
