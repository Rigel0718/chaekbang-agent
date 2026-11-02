"""네 컨텍스트의 모델을 모두 import해 Base.metadata에 등록한다 (Alembic, 테스트용)."""

from app.models import catalog, owner_ops, storefront, supply
from app.models.base import Base

# 컨텍스트별 테이블 소유 (platform/database-schema 스펙).
CONTEXT_TABLES: dict[str, set[str]] = {
    "catalog": {"books", "store_inventory"},
    "storefront": {"chat_logs", "owner_messages", "book_requests"},
    "owner_ops": {"curations", "quotes"},
    "supply": {"institutions", "institution_orders", "order_items", "quote_drafts"},
}

__all__ = ["Base", "CONTEXT_TABLES", "catalog", "owner_ops", "storefront", "supply"]
