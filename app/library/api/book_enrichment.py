from fastapi import APIRouter

from app.library.deps import AdminStaff, Session
from app.library.enrichment_targets import enrichment_counts
from app.library.schemas.catalog import EnrichmentCounts

router = APIRouter(prefix="/book-enrichment", tags=["book-enrichment"])


@router.get("", response_model=EnrichmentCounts)
async def get_enrichment_counts(staff: AdminStaff, session: Session):
    """처리 현황만 본다. 채움은 운영자가 scripts/enrich_books.py로 실행한다."""
    return await enrichment_counts(session, staff.library_id)
