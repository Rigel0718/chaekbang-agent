"""storefront/customer-interactions 스펙 테스트 (저장 계층 제약)."""

from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import assert_rejected, insert


async def test_chat_log_rejects_unknown_role(session: AsyncSession) -> None:
    """[storefront/customer-interactions] 손님 대화 기록 / 허용되지 않은 발화 주체"""
    await insert(
        session, "chat_logs", session_id="s1", role="customer", content="그림책 추천해 주세요"
    )
    await assert_rejected(session, "chat_logs", session_id="s1", role="owner", content="...")


async def test_owner_message_default_status(session: AsyncSession) -> None:
    """[storefront/customer-interactions] 사장님께 전달한 문의 / 기본 상태"""
    row = await insert(session, "owner_messages", content="이 책 다음 권은 언제 나오나요?")
    assert row["status"] == "unread"


async def test_owner_message_rejects_unknown_status(session: AsyncSession) -> None:
    """[storefront/customer-interactions] 사장님께 전달한 문의 / 허용되지 않은 상태"""
    await assert_rejected(session, "owner_messages", content="문의", status="deleted")


async def test_book_request_default_status(session: AsyncSession) -> None:
    """[storefront/customer-interactions] 매장에 없는 책 주문 요청 / 기본 상태"""
    row = await insert(session, "book_requests", title="모모", contact="010-0000-0000")
    assert row["status"] == "received"


async def test_book_request_requires_contact(session: AsyncSession) -> None:
    """[storefront/customer-interactions] 매장에 없는 책 주문 요청 / 연락처 누락"""
    await assert_rejected(session, "book_requests", title="모모", contact=None)
    await assert_rejected(session, "book_requests", title="모모", contact="")


async def test_book_request_without_isbn(session: AsyncSession) -> None:
    """[storefront/customer-interactions] 매장에 없는 책 주문 요청 / ISBN을 확정하지 못한 요청"""
    row = await insert(
        session, "book_requests", title="모모", author="미하엘 엔데", contact="010-0000-0000"
    )
    assert row["isbn"] is None
    assert row["title"] == "모모"
    assert row["contact"] == "010-0000-0000"


async def test_book_request_isbn_must_exist_in_catalog(session: AsyncSession) -> None:
    """[storefront/customer-interactions] 매장에 없는 책 주문 요청 (ISBN은 도서 목록의 도서)"""
    await assert_rejected(
        session, "book_requests", isbn="9780306406157", title="모모", contact="010-0000-0000"
    )
