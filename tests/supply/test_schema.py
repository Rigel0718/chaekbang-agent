"""supply/order-lists, supply/quote-drafts 스펙 테스트 (저장 계층 제약)."""

from sqlalchemy.ext.asyncio import AsyncSession

from tests.helpers import add_institution, assert_rejected, insert


async def _order(session: AsyncSession) -> int:
    institution = await add_institution(session)
    row = await insert(
        session, "institution_orders", institution_id=institution["id"], source_filename="a.xlsx"
    )
    return row["id"]


async def test_order_requires_existing_institution(session: AsyncSession) -> None:
    """[supply/order-lists] 납품 목록과 기관 연결 / 기관 없는 목록"""
    await assert_rejected(
        session, "institution_orders", institution_id=999_999, source_filename="a.xlsx"
    )


async def test_order_default_status(session: AsyncSession) -> None:
    """[supply/order-lists] 납품 목록과 기관 연결 / 기본 진행 상태"""
    institution = await add_institution(session)
    row = await insert(
        session, "institution_orders", institution_id=institution["id"], source_filename="a.xlsx"
    )
    assert row["status"] == "uploaded"


async def test_order_item_before_matching(session: AsyncSession) -> None:
    """[supply/order-lists] 목록 행 원문 보존과 매칭 상태 / 매칭 전 행"""
    order_id = await _order(session)
    row = await insert(
        session, "order_items", order_id=order_id, row_no=1, raw_title="해리포터 2권", quantity=3
    )
    assert row["matched_isbn"] is None
    assert row["match_status"] == "unmatched"
    assert row["raw_title"] == "해리포터 2권"


async def test_order_item_rejects_unknown_match_status(session: AsyncSession) -> None:
    """[supply/order-lists] 목록 행 원문 보존과 매칭 상태 / 허용되지 않은 확인 상태"""
    order_id = await _order(session)
    await assert_rejected(
        session,
        "order_items",
        order_id=order_id,
        row_no=1,
        raw_title="t",
        quantity=1,
        match_status="maybe",
    )


async def test_order_item_rejects_confidence_out_of_range(session: AsyncSession) -> None:
    """[supply/order-lists] 목록 행 원문 보존과 매칭 상태 / 범위를 벗어난 신뢰도"""
    order_id = await _order(session)
    await assert_rejected(
        session,
        "order_items",
        order_id=order_id,
        row_no=1,
        raw_title="t",
        quantity=1,
        confidence=1.5,
    )


async def test_order_item_rejects_zero_quantity(session: AsyncSession) -> None:
    """[supply/order-lists] 목록 행 원문 보존과 매칭 상태 / 수량 0"""
    order_id = await _order(session)
    await assert_rejected(
        session, "order_items", order_id=order_id, row_no=1, raw_title="t", quantity=0
    )


async def test_quote_draft_default_status(session: AsyncSession) -> None:
    """[supply/quote-drafts] 견적서 승인 상태 / 기본 상태"""
    institution = await add_institution(session)
    row = await insert(
        session,
        "quote_drafts",
        institution_id=institution["id"],
        subtotal=100_000,
        discount_amount=10_000,
        total=90_000,
    )
    assert row["status"] == "draft"


async def test_quote_draft_rejects_unknown_status(session: AsyncSession) -> None:
    """[supply/quote-drafts] 견적서 승인 상태 / 허용되지 않은 상태"""
    institution = await add_institution(session)
    await assert_rejected(
        session,
        "quote_drafts",
        institution_id=institution["id"],
        subtotal=0,
        discount_amount=0,
        total=0,
        status="paid",
    )


async def test_quote_draft_rejects_negative_discount(session: AsyncSession) -> None:
    """[supply/quote-drafts] 견적 금액 저장 형식 / 음수 할인액"""
    institution = await add_institution(session)
    await assert_rejected(
        session,
        "quote_drafts",
        institution_id=institution["id"],
        subtotal=10_000,
        discount_amount=-500,
        total=10_500,
    )
