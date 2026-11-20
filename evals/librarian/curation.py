"""큐레이션 시나리오의 준비: 게시본을 넣거나 비운다(`add-approval-flow`).

게시본은 서비스와 같은 service로 만들고 승인한다. 책은 표본에서 추천 가능한 일반 도서 중 id가 작은
3권이다. 평가는 한 트랜잭션에서 시나리오를 차례로 돌리므로, 시나리오마다 앞서 게시된 큐레이션을 모두
내린 뒤 준비한다.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.library.approval import ApprovalStatus
from app.library.models.curation import Curation
from app.library.schemas.curation import CurationWrite
from app.library.services import curations as svc
from evals.librarian.catalog import SampleCatalog
from evals.librarian.scenarios import CURATION_TITLE as TITLE
from evals.librarian.scenarios import CurationSetup


@dataclass(frozen=True)
class CurationBasis:
    title: str | None
    book_ids: tuple[int, ...]


async def _archive_all(session: AsyncSession, library_id: int) -> None:
    published = await session.scalars(
        select(Curation.id).where(
            Curation.library_id == library_id, Curation.status == ApprovalStatus.PUBLISHED
        )
    )
    for curation_id in list(published):
        await svc.unpublish_curation(session, library_id, curation_id)


async def setup_curation(
    session: AsyncSession, catalog: SampleCatalog, setup: CurationSetup | None
) -> CurationBasis | None:
    if setup is None:
        return None
    await _archive_all(session, catalog.library_id)
    if setup is CurationSetup.NONE:
        return CurationBasis(None, ())
    ids = sorted(catalog.recommendable - catalog.children)[:3]
    data = CurationWrite(
        title=TITLE,
        intro="선선한 날 천천히 읽기 좋은 책을 골랐어요",
        items=[{"library_book_id": i, "reason": "도서관 담당자가 고른 책"} for i in ids],
    )
    curation = await svc.create_curation(session, catalog.library_id, None, data, submit=True)
    await svc.approve_curation(session, catalog.library_id, curation.id, None)
    return CurationBasis(TITLE, tuple(ids))
