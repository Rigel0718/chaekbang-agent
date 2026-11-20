"""[library/curations], [library/approval-flow] 큐레이션 API: 관리, 권한, 기관 분리, 게시본."""

from typing import Any

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import Tenant
from tests.helpers import add_held_book, add_loan, add_member, insert


async def _books(session: AsyncSession, library_id: int, n: int = 3) -> list[int]:
    return [(await add_held_book(session, library_id, title=f"책 {i}"))["id"] for i in range(n)]


def _body(ids: list[int], title: str = "공룡 특집") -> dict[str, Any]:
    return {
        "title": title,
        "intro": "소개",
        "items": [{"library_book_id": i, "reason": f"이유 {i}"} for i in ids],
    }


async def _create(client: AsyncClient, ids: list[int], title: str = "공룡 특집") -> dict:
    response = await client.post("/curations", json=_body(ids, title))
    assert response.status_code == 201, response.text
    return response.json()


async def _pending(client: AsyncClient, ids: list[int], title: str = "공룡 특집") -> dict:
    curation = await _create(client, ids, title)
    response = await client.post(f"/curations/{curation['id']}/submit")
    assert response.status_code == 200, response.text
    return response.json()


async def _published(client: AsyncClient, ids: list[int], title: str = "공룡 특집") -> dict:
    curation = await _pending(client, ids, title)
    response = await client.post(f"/curations/{curation['id']}/approve")
    assert response.status_code == 200, response.text
    return response.json()


# --- 관리 API ---


async def test_create(admin_client: AsyncClient, session: AsyncSession, library_a: Tenant) -> None:
    """[library/curations] 큐레이션 관리 API / 만들기"""
    ids = await _books(session, library_a.id)
    body = await _create(admin_client, ids)
    assert body["status"] == "draft"
    assert body["created_by"] == library_a.admin["id"]
    assert [b["library_book_id"] for b in body["books"]] == ids
    assert body["books"][0]["reason"] == f"이유 {ids[0]}"


async def test_list_by_status(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/curations] 큐레이션 관리 API / 상태로 거르기"""
    ids = await _books(session, library_a.id)
    await _create(admin_client, ids, "초안")
    pending = await _pending(admin_client, ids, "대기")
    response = await admin_client.get("/curations", params={"status": "pending_approval"})
    assert [c["id"] for c in response.json()] == [pending["id"]]


async def test_edit_after_reject(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/curations] 큐레이션 관리 API / 고친 뒤 제출"""
    ids = await _books(session, library_a.id, 4)
    curation = await _pending(admin_client, ids[:3])
    rejected = await admin_client.post(
        f"/curations/{curation['id']}/reject", json={"reason": "한 권 바꿔 주세요"}
    )
    assert rejected.json()["status"] == "draft"
    assert rejected.json()["rejected_reason"] == "한 권 바꿔 주세요"
    patched = await admin_client.patch(f"/curations/{curation['id']}", json=_body(ids[1:]))
    assert patched.status_code == 200
    submitted = await admin_client.post(f"/curations/{curation['id']}/submit")
    assert submitted.json()["status"] == "pending_approval"
    assert [b["library_book_id"] for b in submitted.json()["books"]] == ids[1:]


async def test_validation_and_conflicts(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/curations] 내용·소장 규칙과 [library/approval-flow] 상태 전이의 응답 코드"""
    ids = await _books(session, library_a.id)
    assert (await admin_client.post("/curations", json=_body(ids[:2]))).status_code == 422
    withdrawn = (await add_held_book(session, library_a.id, "withdrawn"))["id"]
    response = await admin_client.post("/curations", json=_body([*ids[:2], withdrawn]))
    assert response.status_code == 409
    assert str(withdrawn) in response.json()["detail"]
    curation = await _pending(admin_client, ids)
    assert (
        await admin_client.patch(f"/curations/{curation['id']}", json=_body(ids))
    ).status_code == 409
    assert (await admin_client.delete(f"/curations/{curation['id']}")).status_code == 409
    assert (await admin_client.post(f"/curations/{curation['id']}/unpublish")).status_code == 409
    reject = await admin_client.post(f"/curations/{curation['id']}/reject", json={})
    assert reject.status_code == 422


async def test_request_library_id_rejected(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant, library_b: Tenant
) -> None:
    """[library/approval-flow] 승인의 기관 분리: 요청 본문의 기관 값은 받지 않는다"""
    ids = await _books(session, library_a.id)
    response = await admin_client.post(
        "/curations", json={**_body(ids), "library_id": library_b.id}
    )
    assert response.status_code == 422


async def test_delete_draft(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/curations] 큐레이션 관리 API: 초안 지우기"""
    curation = await _create(admin_client, await _books(session, library_a.id))
    assert (await admin_client.delete(f"/curations/{curation['id']}")).status_code == 204
    assert (await admin_client.get(f"/curations/{curation['id']}")).status_code == 404


# --- 승인 권한 ---


async def test_kiosk_cannot_approve(
    admin_client: AsyncClient, kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/approval-flow] 승인 권한 / 키오스크의 승인"""
    curation = await _pending(admin_client, await _books(session, library_a.id))
    for path in ("approve", "submit", "unpublish"):
        assert (await kiosk_client.post(f"/curations/{curation['id']}/{path}")).status_code == 403
    assert (
        await kiosk_client.post(f"/curations/{curation['id']}/reject", json={"reason": "x"})
    ).status_code == 403
    assert (await kiosk_client.get("/curations")).status_code == 403
    assert (await kiosk_client.post("/curations", json=_body([1, 2, 3]))).status_code == 403
    stored = await admin_client.get(f"/curations/{curation['id']}")
    assert stored.json()["status"] == "pending_approval"


async def test_no_token(
    client: AsyncClient, admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/approval-flow] 승인 권한 / 토큰 없이 승인"""
    curation = await _pending(admin_client, await _books(session, library_a.id))
    assert (await client.post(f"/curations/{curation['id']}/approve")).status_code == 401
    assert (await client.get("/librarian/curations")).status_code == 401


# --- 기관 분리 ---


async def test_other_library_approve(
    admin_client: AsyncClient,
    admin_client_b: AsyncClient,
    session: AsyncSession,
    library_b: Tenant,
) -> None:
    """[library/approval-flow] 승인의 기관 분리 / 다른 기관의 초안 승인 (API)"""
    theirs = await _pending(admin_client_b, await _books(session, library_b.id))
    assert (await admin_client.post(f"/curations/{theirs['id']}/approve")).status_code == 404
    assert (await admin_client.get(f"/curations/{theirs['id']}")).status_code == 404
    stored = await admin_client_b.get(f"/curations/{theirs['id']}")
    assert stored.json()["status"] == "pending_approval"


async def test_other_library_list(
    admin_client: AsyncClient,
    admin_client_b: AsyncClient,
    session: AsyncSession,
    library_a: Tenant,
    library_b: Tenant,
) -> None:
    """[library/approval-flow] 승인의 기관 분리 / 다른 기관의 초안 목록 (API)"""
    mine = await _create(admin_client, await _books(session, library_a.id))
    await _create(admin_client_b, await _books(session, library_b.id))
    assert [c["id"] for c in (await admin_client.get("/curations")).json()] == [mine["id"]]


# --- 게시본 읽기 ---


async def test_published_only(
    admin_client: AsyncClient, kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/curations] 게시본 읽기 / 게시된 것만"""
    ids = await _books(session, library_a.id)
    await _create(admin_client, ids, "초안")
    await _pending(admin_client, ids, "대기")
    published = await _published(admin_client, ids, "게시")
    archived = await _published(admin_client, ids, "내림")
    await admin_client.post(f"/curations/{archived['id']}/unpublish")
    response = await kiosk_client.get("/librarian/curations")
    assert response.status_code == 200
    [only] = response.json()
    assert only["id"] == published["id"]
    assert only["title"] == "게시"
    assert only["published_at"] is not None
    assert set(only) == {"id", "title", "intro", "published_at", "books"}
    assert (await admin_client.get("/librarian/curations")).status_code == 200


async def test_published_other_library(
    admin_client_b: AsyncClient, kiosk_client: AsyncClient, session: AsyncSession, library_b: Tenant
) -> None:
    """[library/curations] 게시본 읽기 / 다른 기관의 게시본"""
    await _published(admin_client_b, await _books(session, library_b.id))
    assert (await kiosk_client.get("/librarian/curations")).json() == []


# --- 개인정보 ---

PERSONAL_KEYS = {"member", "member_id", "member_number", "member_name", "name", "donor", "loans"}


def _keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


async def test_no_personal_values(
    admin_client: AsyncClient, kiosk_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/curations] 큐레이션의 개인정보 / 응답 필드"""
    ids = await _books(session, library_a.id, 2)
    loaned = await add_held_book(session, library_a.id, "available", title="빌린 책")
    holding = await insert(
        session,
        "holdings",
        library_id=library_a.id,
        library_book_id=loaned["id"],
        accession_number="DONOR-1",
        acquisition_type="donated",
        donor="기증자홍길동",
    )
    member = await add_member(session, library_a.id, "M-SECRET-77", name="회원김비밀")
    await add_loan(session, holding, member)
    curation = await _published(admin_client, [*ids, loaned["id"]])
    detail = (await admin_client.get(f"/curations/{curation['id']}")).text
    public = (await kiosk_client.get("/librarian/curations")).text
    for text in (detail, public):
        for secret in ("M-SECRET-77", "회원김비밀", "기증자홍길동"):
            assert secret not in text
    import json

    for body in (json.loads(detail), json.loads(public)):
        assert not (_keys(body) & PERSONAL_KEYS)
