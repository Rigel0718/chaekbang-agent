"""[library/approval-flow] 재시작 뒤 이어짐.

다른 테스트와 달리 트랜잭션 되돌림을 쓰지 않는다. 엔진 A로 승인 대기 큐레이션을 커밋하고 연결을 모두
닫은 뒤, 새 엔진 B로 띄운 앱에서 HTTP로 승인한다. 끝나면 만든 기관을 지운다.
"""

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.db import get_session
from app.library.schemas.curation import CurationWrite
from app.library.services import curations as svc
from app.main import app
from tests.conftest import _tenant, make_client
from tests.helpers import add_held_book

TABLES = ("curations", "holdings", "library_books", "staff_sessions", "staff_users")


async def _cleanup(url: str, library_id: int) -> None:
    engine = create_async_engine(url, poolclass=NullPool)
    try:
        async with engine.begin() as conn:
            for table in TABLES:
                await conn.execute(
                    text(f"DELETE FROM {table} WHERE library_id = :id"), {"id": library_id}
                )
            await conn.execute(text("DELETE FROM libraries WHERE id = :id"), {"id": library_id})
    finally:
        await engine.dispose()


async def test_approve_from_new_connection(migrated_db: str) -> None:
    """[library/approval-flow] 재시작 뒤 이어짐 / 새 연결에서 승인"""
    first = create_async_engine(migrated_db, poolclass=NullPool)
    async with AsyncSession(first, expire_on_commit=False) as session:
        tenant = await _tenant(session, "재시작 도서관", "internal", "restart")
        ids = [
            (await add_held_book(session, tenant.id, title=f"재시작 책 {i}"))["id"]
            for i in range(3)
        ]
        await session.commit()
        data = CurationWrite(
            title="재시작 특집",
            items=[{"library_book_id": i, "reason": "이유"} for i in ids],
        )
        curation = await svc.create_curation(
            session, tenant.id, tenant.admin["id"], data, submit=True
        )
        curation_id = curation.id
    await first.dispose()

    second = create_async_engine(migrated_db, poolclass=NullPool)
    sessions = async_sessionmaker(second, expire_on_commit=False)

    async def override() -> AsyncIterator[AsyncSession]:
        async with sessions() as session:
            yield session

    app.dependency_overrides[get_session] = override
    try:
        # 앱 상태에 승인과 관련된 값이 없다. 승인은 DB 행만으로 이어진다.
        assert not [
            k for k in vars(app.state).get("_state", {}) if "curation" in k or "approv" in k
        ]
        async with make_client(tenant.admin_token) as admin:
            approved = await admin.post(f"/curations/{curation_id}/approve")
            assert approved.status_code == 200, approved.text
            assert approved.json()["status"] == "published"
        async with make_client(tenant.kiosk_token) as kiosk:
            published = (await kiosk.get("/librarian/curations")).json()
        assert [c["id"] for c in published] == [curation_id]
    finally:
        app.dependency_overrides.clear()
        await second.dispose()
        await _cleanup(migrated_db, tenant.id)
