from fastapi import APIRouter

from app.core.deps import AdminStaff, Session
from app.schemas.catalog import EnrichmentCounts
from app.services import book_enrichment

router = APIRouter(prefix="/book-enrichment", tags=["book-enrichment"])


@router.get("", response_model=EnrichmentCounts)
async def get_enrichment_counts(staff: AdminStaff, session: Session):
    """처리 현황만 본다. 채움은 운영자가 scripts/enrich_books.py로 실행한다."""
    return await book_enrichment.enrichment_counts(session, staff.library_id)
