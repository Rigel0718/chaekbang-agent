"""[library/overdue-notices] 안내문 틀, 승인(확정), 쓰는 틀, 연체 안내 목록, 기관 분리."""

from datetime import date, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from tests.conftest import Tenant
from tests.helpers import add_held_book, add_loan, add_member, fetch, insert

TODAY = date(2026, 11, 21)
BODY = "{이름}님, '{서명}'의 반납 예정일({반납예정일})이 {연체일수}일 지났습니다. {도서관}"


@pytest.fixture(autouse=True)
def _today(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clock, "today", lambda: TODAY)


async def _draft(client: AsyncClient, body: str = BODY) -> dict[str, Any]:
    response = await client.post("/overdue-notice-templates", json={"body": body})
    assert response.status_code == 201, response.text
    return response.json()


async def _pending(client: AsyncClient, body: str = BODY) -> dict[str, Any]:
    template = await _draft(client, body)
    response = await client.post(f"/overdue-notice-templates/{template['id']}/submit")
    assert response.status_code == 200, response.text
    return response.json()


async def _confirmed(client: AsyncClient, body: str = BODY) -> dict[str, Any]:
    template = await _pending(client, body)
    response = await client.post(f"/overdue-notice-templates/{template['id']}/approve")
    assert response.status_code == 200, response.text
    return response.json()


async def _overdue(
    session: AsyncSession,
    library_id: int,
    number: str,
    name: str,
    title: str,
    due_on: date,
    *,
    phone: str | None = None,
    accession: str | None = None,
) -> Any:
    book = await add_held_book(session, library_id, title=title)
    holding = await session.execute(
        text("SELECT * FROM holdings WHERE library_book_id = :id"), {"id": book["id"]}
    )
    holding_row = holding.mappings().one()
    if accession:
        await session.execute(
            text("UPDATE holdings SET accession_number = :a WHERE id = :id"),
            {"a": accession, "id": holding_row["id"]},
        )
        holding_row = await fetch(session, "holdings", holding_row["id"])
    existing = await session.execute(
        text("SELECT * FROM members WHERE library_id = :lib AND member_number = :n"),
        {"lib": library_id, "n": number},
    )
    member = existing.mappings().one_or_none()
    if member is None:
        member = await insert(
            session, "members", library_id=library_id, member_number=number, name=name, phone=phone
        )
    return await add_loan(
        session, holding_row, member, loaned_on=due_on - timedelta(days=14), due_on=due_on
    )


# --- 틀 내용 ---


async def test_create_template(admin_client: AsyncClient) -> None:
    """[library/overdue-notices] 안내문 틀 내용 / 정상 틀"""
    template = await _draft(admin_client)
    assert template["status"] == "draft"
    assert template["body"] == BODY
    assert template["in_use"] is False


@pytest.mark.parametrize(
    ("body", "reason"),
    [
        ("{이름}님 {서명} {반납예정일} {전화번호}", "모르는 자리표시"),
        ("{이름}님 {서명} 반납 예정일이 지났습니다", "필수 자리표시 빠짐: 반납예정일"),
        ("{이름}님 {반납예정일}까지 반납해 주세요", "필수 자리표시 빠짐: 서명"),
        ("{서명} {반납예정일} " + "가" * 300, "길이 초과"),
    ],
)
async def test_invalid_body_rejected(
    admin_client: AsyncClient, session: AsyncSession, body: str, reason: str
) -> None:
    """[library/overdue-notices] 안내문 틀 내용 / 모르는 자리표시, 필수 자리표시 빠짐, 길이 초과"""
    response = await admin_client.post("/overdue-notice-templates", json={"body": body})
    assert response.status_code == 422, reason
    assert (await admin_client.get("/overdue-notice-templates")).json() == []


async def test_body_at_limit_is_accepted(admin_client: AsyncClient) -> None:
    """[library/overdue-notices] 안내문 틀 내용 / 정상 틀 (300자 경계)"""
    body = "{서명} {반납예정일} " + "가" * (300 - len("{서명} {반납예정일} "))
    assert len(body) == 300
    await _draft(admin_client, body)


async def test_other_braces_are_not_code(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/overdue-notices] 안내문 틀 내용 / 채우기는 정해진 자리표시만 바꾼다"""
    await _confirmed(admin_client, "{서명} {반납예정일} ({도서관}.__class__)")
    await _overdue(session, library_a.id, "M0001", "김이용", "공룡", date(2026, 11, 10))
    lines = (await admin_client.get("/overdue-notices/today")).json()["lines"]
    assert lines[0]["message"].endswith(".__class__)")


# --- 개인정보 ---


@pytest.mark.parametrize("value", ["010-1234-5678", "01012345678", "mail@example.com"])
async def test_personal_value_in_body_rejected(admin_client: AsyncClient, value: str) -> None:
    """[library/overdue-notices] 틀의 개인정보 거부 / 전화번호가 든 틀"""
    response = await admin_client.post(
        "/overdue-notice-templates", json={"body": f"{{서명}} {{반납예정일}} 문의 {value}"}
    )
    assert response.status_code == 422
    assert value not in response.text
    assert (await admin_client.get("/overdue-notice-templates")).json() == []


async def test_member_number_in_body_rejected(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/overdue-notices] 틀의 개인정보 거부 / 회원번호가 든 틀"""
    await add_member(session, library_a.id, "M7788", "김이용")
    response = await admin_client.post(
        "/overdue-notice-templates", json={"body": "M7788님 {서명} {반납예정일}"}
    )
    assert response.status_code == 422
    assert "M7788" not in response.text
    template = await _draft(admin_client)
    patched = await admin_client.patch(
        f"/overdue-notice-templates/{template['id']}",
        json={"body": "M7788님 {서명} {반납예정일}"},
    )
    assert patched.status_code == 422
    assert (await admin_client.get(f"/overdue-notice-templates/{template['id']}")).json()[
        "body"
    ] == BODY


# --- 관리와 승인 ---


async def test_list_by_status(admin_client: AsyncClient) -> None:
    """[library/overdue-notices] 안내문 틀 관리 API / 상태로 거르기"""
    await _draft(admin_client)
    pending = await _pending(admin_client)
    rows = (
        await admin_client.get("/overdue-notice-templates", params={"status": "pending_approval"})
    ).json()
    assert [r["id"] for r in rows] == [pending["id"]]


async def test_reject_then_edit_and_submit(admin_client: AsyncClient) -> None:
    """[library/overdue-notices] 안내문 틀 관리 API / 반려 뒤 고쳐 제출"""
    pending = await _pending(admin_client)
    rejected = await admin_client.post(
        f"/overdue-notice-templates/{pending['id']}/reject", json={"reason": "말투가 딱딱해요"}
    )
    assert rejected.json()["status"] == "draft"
    assert rejected.json()["rejected_reason"] == "말투가 딱딱해요"
    edited = await admin_client.patch(
        f"/overdue-notice-templates/{pending['id']}", json={"body": "{서명} {반납예정일} 부탁해요"}
    )
    assert edited.json()["body"] == "{서명} {반납예정일} 부탁해요"
    submitted = await admin_client.post(f"/overdue-notice-templates/{pending['id']}/submit")
    assert submitted.json()["status"] == "pending_approval"
    assert submitted.json()["body"] == "{서명} {반납예정일} 부탁해요"


async def test_approval_records_confirmation(admin_client: AsyncClient, library_a: Tenant) -> None:
    """[library/overdue-notices] 승인하면 확정 / 승인 기록"""
    template = await _confirmed(admin_client)
    assert template["status"] == "confirmed"
    assert template["approved_by"] == library_a.admin["id"]
    assert template["approved_at"] is not None
    assert template["confirmed_at"] is not None
    assert template["in_use"] is True


async def test_confirmed_template_is_frozen(admin_client: AsyncClient) -> None:
    """[library/overdue-notices] 승인하면 확정 / 확정된 틀 고치기"""
    template = await _confirmed(admin_client)
    url = f"/overdue-notice-templates/{template['id']}"
    assert (await admin_client.patch(url, json={"body": "{서명} {반납예정일}"})).status_code == 409
    assert (await admin_client.delete(url)).status_code == 409
    assert (await admin_client.post(f"{url}/reject", json={"reason": "x"})).status_code == 409
    assert (await admin_client.post(f"{url}/approve")).status_code == 409
    assert (await admin_client.get(url)).json()["body"] == BODY


async def test_draft_cannot_be_approved(admin_client: AsyncClient) -> None:
    """[library/approval-flow] 상태 전이 / 초안을 바로 승인 (연체 안내 틀)"""
    template = await _draft(admin_client)
    response = await admin_client.post(f"/overdue-notice-templates/{template['id']}/approve")
    assert response.status_code == 409


async def test_delete_draft(admin_client: AsyncClient) -> None:
    """[library/overdue-notices] 안내문 틀 관리 API / 초안 지우기"""
    template = await _draft(admin_client)
    response = await admin_client.delete(f"/overdue-notice-templates/{template['id']}")
    assert response.status_code == 204
    assert (await admin_client.get("/overdue-notice-templates")).json() == []


# --- 쓰는 틀 ---


async def test_latest_confirmed_template_is_used(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/overdue-notices] 쓰는 틀 / 새로 확정한 틀"""
    await _overdue(session, library_a.id, "M0001", "김이용", "공룡", date(2026, 11, 10))
    first = await _confirmed(admin_client, "A틀 {서명} {반납예정일}")
    second = await _confirmed(admin_client, "B틀 {서명} {반납예정일}")
    body = (await admin_client.get("/overdue-notices/today")).json()
    assert body["template_id"] == second["id"]
    assert body["lines"][0]["message"].startswith("B틀")
    listed = {
        t["id"]: t["in_use"] for t in (await admin_client.get("/overdue-notice-templates")).json()
    }
    assert listed == {first["id"]: False, second["id"]: True}


async def test_pending_template_is_not_used(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/overdue-notices] 쓰는 틀 / 승인 대기 틀"""
    await _overdue(session, library_a.id, "M0001", "김이용", "공룡", date(2026, 11, 10))
    first = await _confirmed(admin_client, "A틀 {서명} {반납예정일}")
    await _pending(admin_client, "B틀 {서명} {반납예정일}")
    body = (await admin_client.get("/overdue-notices/today")).json()
    assert body["template_id"] == first["id"]
    assert body["lines"][0]["message"].startswith("A틀")


# --- 연체 안내 목록 ---


async def test_filled_message(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/overdue-notices] 연체 안내 목록 / 채운 문안"""
    await session.execute(
        text("UPDATE libraries SET name = '햇살작은도서관' WHERE id = :id"), {"id": library_a.id}
    )
    await _overdue(
        session, library_a.id, "M0001", "김이용", "공룡 대백과", date(2026, 11, 10),
        phone="01012345678", accession="A-1",
    )  # fmt: skip
    await _confirmed(admin_client)
    body = (await admin_client.get("/overdue-notices/today")).json()
    assert (body["today"], body["total"]) == ("2026-11-21", 1)
    line = body["lines"][0]
    assert line["message"] == (
        "김이용님, '공룡 대백과'의 반납 예정일(2026-11-10)이 11일 지났습니다. 햇살작은도서관"
    )
    assert (line["member_number"], line["name"], line["phone"]) == (
        "M0001",
        "김이용",
        "01012345678",
    )
    assert (line["accession_number"], line["due_on"], line["overdue_days"]) == (
        "A-1",
        "2026-11-10",
        11,
    )


async def test_official_title_is_preferred(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/overdue-notices] 연체 안내 목록 / 채운 문안 (공식 서명 먼저)"""
    book = await add_held_book(
        session, library_a.id, title="기관 서명", official={"title": "공식 서명"}
    )
    holding = (
        (
            await session.execute(
                text("SELECT * FROM holdings WHERE library_book_id = :id"), {"id": book["id"]}
            )
        )
        .mappings()
        .one()
    )
    member = await add_member(session, library_a.id, "M0001")
    await add_loan(session, holding, member, loaned_on=date(2026, 10, 18), due_on=date(2026, 11, 1))
    await _confirmed(admin_client)
    lines = (await admin_client.get("/overdue-notices/today")).json()["lines"]
    assert lines[0]["title"] == "공식 서명"
    assert "'공식 서명'" in lines[0]["message"]


async def test_returned_and_due_today_excluded(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/overdue-notices] 연체 안내 목록 / 반납했거나 아직 기한 안"""
    returned = await _overdue(session, library_a.id, "M0001", "김이용", "반납됨", date(2026, 11, 5))
    await session.execute(
        text("UPDATE loans SET returned_on = :d WHERE id = :id"),
        {"d": date(2026, 11, 20), "id": returned["id"]},
    )
    await _overdue(session, library_a.id, "M0002", "박이용", "오늘까지", TODAY)
    await _overdue(session, library_a.id, "M0003", "최이용", "하루 지남", TODAY - timedelta(days=1))
    await _confirmed(admin_client)
    body = (await admin_client.get("/overdue-notices/today")).json()
    assert [(line["title"], line["overdue_days"]) for line in body["lines"]] == [("하루 지남", 1)]
    assert body["total"] == 1


async def test_member_without_phone(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/overdue-notices] 연체 안내 목록 / 전화번호 없는 회원"""
    await _overdue(session, library_a.id, "M0001", "김이용", "공룡", date(2026, 11, 10))
    await _confirmed(admin_client)
    line = (await admin_client.get("/overdue-notices/today")).json()["lines"][0]
    assert line["phone"] is None
    assert "김이용" in line["message"]


async def test_lines_sorted_by_member_then_due_date(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/overdue-notices] 연체 안내 목록 순서 / 같은 회원의 두 권"""
    await _overdue(session, library_a.id, "M0002", "박이용", "둘의 늦은 책", date(2026, 11, 15))
    await _overdue(session, library_a.id, "M0001", "김이용", "하나의 책", date(2026, 11, 18))
    await _overdue(session, library_a.id, "M0002", "박이용", "둘의 이른 책", date(2026, 11, 3))
    await _confirmed(admin_client)
    lines = (await admin_client.get("/overdue-notices/today")).json()["lines"]
    assert [(line["member_number"], line["title"]) for line in lines] == [
        ("M0001", "하나의 책"),
        ("M0002", "둘의 이른 책"),
        ("M0002", "둘의 늦은 책"),
    ]


async def test_no_confirmed_template(admin_client: AsyncClient) -> None:
    """[library/overdue-notices] 목록은 저장하지 않음 / 틀 없음"""
    assert (await admin_client.get("/overdue-notices/today")).status_code == 409
    await _pending(admin_client)
    assert (await admin_client.get("/overdue-notices/today")).status_code == 409


async def test_list_does_not_write(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/overdue-notices] 목록은 저장하지 않음 / 저장 없음"""
    await _overdue(session, library_a.id, "M0001", "김이용", "공룡", date(2026, 11, 10))
    await _confirmed(admin_client)

    async def snapshot() -> list[tuple]:
        rows = []
        for table in ("overdue_notice_templates", "loans", "members", "holdings"):
            result = await session.execute(text(f"SELECT * FROM {table} ORDER BY id"))
            rows.append((table, [tuple(r) for r in result]))
        return rows

    before = await snapshot()
    assert (await admin_client.get("/overdue-notices/today")).status_code == 200
    assert (await admin_client.get("/overdue-notices/today")).status_code == 200
    assert await snapshot() == before


# --- 권한 ---


async def test_kiosk_forbidden(kiosk_client: AsyncClient) -> None:
    """[library/overdue-notices] 연체 안내 권한 / 키오스크의 목록 요청"""
    assert (await kiosk_client.get("/overdue-notices/today")).status_code == 403
    assert (
        await kiosk_client.post("/overdue-notice-templates", json={"body": BODY})
    ).status_code == 403
    assert (await kiosk_client.get("/overdue-notice-templates")).status_code == 403
    assert (await kiosk_client.post("/overdue-notice-templates/1/approve")).status_code == 403


async def test_no_token(_app: None) -> None:
    """[library/overdue-notices] 연체 안내 권한 / 토큰 없이 목록 요청"""
    from tests.conftest import make_client

    async with make_client(None) as client:
        assert (await client.get("/overdue-notices/today")).status_code == 401
        assert (await client.post("/overdue-notice-templates/1/approve")).status_code == 401


# --- 기관 분리와 외부 대출 ---


async def _make_b_internal(session: AsyncSession, library_b: Tenant) -> None:
    await session.execute(
        text("UPDATE libraries SET loan_mode = 'internal' WHERE id = :id"), {"id": library_b.id}
    )


async def test_other_library_template_is_404(
    admin_client: AsyncClient,
    admin_client_b: AsyncClient,
    session: AsyncSession,
    library_b: Tenant,
) -> None:
    """[library/overdue-notices] 연체 안내의 기관 분리 / 다른 기관의 틀 승인"""
    await _make_b_internal(session, library_b)
    theirs = await _pending(admin_client_b)
    url = f"/overdue-notice-templates/{theirs['id']}"
    assert (await admin_client.post(f"{url}/approve")).status_code == 404
    assert (await admin_client.get(url)).status_code == 404
    assert (await admin_client.patch(url, json={"body": BODY})).status_code == 404
    assert (await admin_client.delete(url)).status_code == 404
    assert (await admin_client.get("/overdue-notice-templates")).json() == []
    assert (await admin_client_b.get(url)).json()["status"] == "pending_approval"


async def test_other_library_overdue_not_listed(
    admin_client: AsyncClient,
    session: AsyncSession,
    library_a: Tenant,
    library_b: Tenant,
) -> None:
    """[library/overdue-notices] 연체 안내의 기관 분리 / 다른 기관의 연체"""
    await _make_b_internal(session, library_b)
    await _overdue(session, library_a.id, "M0001", "가기관회원", "A의 책", date(2026, 11, 10))
    await _overdue(session, library_b.id, "M0001", "나기관회원", "B의 책", date(2026, 11, 10))
    await _confirmed(admin_client)
    body = (await admin_client.get("/overdue-notices/today")).json()
    assert [line["title"] for line in body["lines"]] == ["A의 책"]
    assert "나기관회원" not in str(body)


async def test_other_library_confirmed_template_not_used(
    admin_client: AsyncClient,
    admin_client_b: AsyncClient,
    session: AsyncSession,
    library_b: Tenant,
) -> None:
    """[library/overdue-notices] 연체 안내의 기관 분리 / 다른 기관의 확정 틀"""
    await _make_b_internal(session, library_b)
    await _confirmed(admin_client_b)
    assert (await admin_client.get("/overdue-notices/today")).status_code == 409


async def test_external_library_is_blocked(
    admin_client_b: AsyncClient, session: AsyncSession, library_b: Tenant
) -> None:
    """[library/overdue-notices] 외부 대출 기관의 연체 안내 / 틀 만들기, 목록"""
    created = await admin_client_b.post("/overdue-notice-templates", json={"body": BODY})
    assert created.status_code == 409
    assert "기존 대출 프로그램" in created.json()["detail"]
    assert (await admin_client_b.get("/overdue-notice-templates")).status_code == 409
    assert (await admin_client_b.get("/overdue-notices/today")).status_code == 409
    assert (await admin_client_b.post("/overdue-notice-templates/1/submit")).status_code == 409
    assert (await admin_client_b.post("/overdue-notice-templates/1/approve")).status_code == 409
    count = await session.scalar(
        text("SELECT count(*) FROM overdue_notice_templates WHERE library_id = :id"),
        {"id": library_b.id},
    )
    assert count == 0


async def test_short_member_number_is_not_matched(
    admin_client: AsyncClient, session: AsyncSession, library_a: Tenant
) -> None:
    """[library/overdue-notices] 틀의 개인정보 거부 / 4자보다 짧은 회원번호는 맞춰 보지 않음"""
    await add_member(session, library_a.id, "M77", "김이용")
    await _draft(admin_client, "{서명} {반납예정일} M77")
