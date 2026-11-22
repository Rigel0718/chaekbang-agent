"""모든 모델을 import해 Base.metadata에 등록한다 (Alembic, 테스트용)."""

from app.agent import models as agent
from app.central import models as central
from app.core.model_base import Base
from app.features.children import models as children
from app.library.models import (
    book_request,
    catalog,
    chat,
    circulation,
    curation,
    embedding,
    guide,
    library,
    overdue_notice,
)

# 기관 데이터 테이블 구분 (platform/database-schema 스펙).
# 공통 테이블은 기관 구분 없이 함께 쓰고, 기관 데이터 테이블은 모두 NOT NULL library_id를 가진다.
SHARED_TABLES: set[str] = {"libraries", "books", "book_contributors", "official_book_embeddings"}
TENANT_TABLES: set[str] = {
    "staff_users",
    "staff_sessions",
    "library_books",
    "library_book_audiences",
    "holdings",
    "holding_imports",
    "members",
    "loans",
    "agent_runs",
    "agent_steps",
    "chat_sessions",
    "chat_messages",
    "recommendation_events",
    "library_guides",
    "library_opening_hours",
    "library_closures",
    "library_guide_entries",
    "book_embeddings",
    "curations",
    "curation_items",
    "overdue_notice_templates",
    "book_requests",
}

__all__ = [
    "SHARED_TABLES",
    "TENANT_TABLES",
    "Base",
    "agent",
    "book_request",
    "catalog",
    "central",
    "chat",
    "children",
    "circulation",
    "curation",
    "embedding",
    "guide",
    "library",
    "overdue_notice",
]
