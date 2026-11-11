"""[library/library-guide] 안내 API와 [library/staff-auth] 키오스크의 안내 접근."""

from datetime import date

import pytest
from httpx import AsyncClient

from app.core import clock
from tests.conftest import Tenant

WED = date(2026, 11, 11)

HOURS = [{"weekday": d, "opens_at": "09:00", "closes_at": "18:00"} for d in (2, 3, 4, 5, 6)] + [
    {"weekday": 1, "opens_at": "09:00", "closes_at": "12:00"},
    {"weekday": 1, "opens_at": "13:00", "closes_at": "18:00"},
]
ENTRIES = [
    {"kind": "facility", "title": "화장실", "body": "1층 출입문 오른쪽"},
    {"kind": "facility", "title": "어린이 자료실", "body": "2층"},
    {"kind": "rule", "title": "음식물", "body": "열람실에서는 음식을 먹을 수 없어요"},
]
GUIDE = {
    "contact_phone": "031-000-0000",
    "loan_limit": 5,
    "closed_on_public_holidays": True,
    "hours": HOURS,
    "entries": ENTRIES,
}


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch: pytest.MonkeyPatch) -> date:
    monkeypatch.setattr(clock, "today", lambda: WED)
    return WED


async def test_first_guide(kiosk_client: AsyncClient) -> None:
    """[library/library-guide] 안내 정보 보관 / 처음 쓰는 기관"""
    res = await kiosk_client.get("/library/guide")
    assert res.status_code == 200
    body = res.json()
    assert body["registered"] is False
    assert body["contact_phone"] is None
    assert all(day["spans"] == [] for day in body["weekly_hours"])
    assert body["entries"] == []
    assert body["due_on_closed_day"] == "next_open_day"
    assert body["loan_days"] == 14


async def test_lunch_break(admin_client: AsyncClient) -> None:
    """[library/library-guide] 안내 정보 보관 / 점심시간이 있는 요일"""
    res = await admin_client.put("/library/guide", json=GUIDE)
    assert res.status_code == 200
    tuesday = res.json()["weekly_hours"][1]
    assert tuesday["weekday_label"] == "화"
    assert tuesday["spans"] == [
        {"opens_at": "09:00:00", "closes_at": "12:00:00"},
        {"opens_at": "13:00:00", "closes_at": "18:00:00"},
    ]


async def test_replace_whole_guide(admin_client: AsyncClient) -> None:
    """[library/library-guide] 안내 정보 수정 / 전체 바꾸기"""
    await admin_client.put("/library/guide", json=GUIDE)
    res = await admin_client.put("/library/guide", json={"entries": ENTRIES[:1]})
    assert res.status_code == 200
    body = (await admin_client.get("/library/guide")).json()
    assert [e["title"] for e in body["entries"]] == ["화장실"]
    assert all(day["spans"] == [] for day in body["weekly_hours"])


async def test_overlapping_spans(admin_client: AsyncClient) -> None:
    """[library/library-guide] 안내 정보 수정 / 겹치는 구간"""
    await admin_client.put("/library/guide", json=GUIDE)
    bad = {
        "hours": [
            {"weekday": 1, "opens_at": "09:00", "closes_at": "13:00"},
            {"weekday": 1, "opens_at": "12:00", "closes_at": "18:00"},
        ]
    }
    res = await admin_client.put("/library/guide", json=bad)
    assert res.status_code == 422
    body = (await admin_client.get("/library/guide")).json()
    assert body["contact_phone"] == "031-000-0000"
    assert len(body["entries"]) == 3


async def test_closes_before_opens(admin_client: AsyncClient) -> None:
    """[library/library-guide] 안내 정보 수정 / 닫는 시각이 앞"""
    bad = {"hours": [{"weekday": 2, "opens_at": "18:00", "closes_at": "09:00"}]}
    assert (await admin_client.put("/library/guide", json=bad)).status_code == 422


async def test_guide_limits(admin_client: AsyncClient) -> None:
    too_many = [{"kind": "notice", "title": f"알림 {i}", "body": "내용"} for i in range(51)]
    assert (await admin_client.put("/library/guide", json={"entries": too_many})).status_code == 422
    long_body = [{"kind": "notice", "title": "알림", "body": "가" * 501}]
    assert (
        await admin_client.put("/library/guide", json={"entries": long_body})
    ).status_code == 422
    bad_phone = {"contact_phone": "담당자 김OO 010-1234-5678"}
    assert (await admin_client.put("/library/guide", json=bad_phone)).status_code == 422


async def test_kiosk_cannot_replace_guide(
    kiosk_client: AsyncClient, admin_client: AsyncClient
) -> None:
    """[library/library-guide] 안내 정보 수정 / 키오스크의 수정"""
    res = await kiosk_client.put("/library/guide", json=GUIDE)
    assert res.status_code == 403
    assert (await admin_client.get("/library/guide")).json()["registered"] is False


async def test_add_closure(admin_client: AsyncClient) -> None:
    """[library/library-guide] 임시 휴관일 / 휴관일 등록"""
    await admin_client.put("/library/guide", json=GUIDE)
    res = await admin_client.post(
        "/library/closures", json={"closed_on": "2026-11-13", "reason": "소독"}
    )
    assert res.status_code == 201
    assert res.json()["reason"] == "소독"
    days = (await admin_client.get("/library/guide")).json()["next_days"]
    friday = next(d for d in days if d["date"] == "2026-11-13")
    assert (friday["status"], friday["closed_reason"]) == ("closed", "임시 휴관: 소독")


async def test_duplicate_closure(admin_client: AsyncClient) -> None:
    """[library/library-guide] 임시 휴관일 / 같은 날짜 두 번"""
    assert (
        await admin_client.post("/library/closures", json={"closed_on": "2026-11-20"})
    ).status_code == 201
    res = await admin_client.post("/library/closures", json={"closed_on": "2026-11-20"})
    assert res.status_code == 409


async def test_delete_other_library_closure(
    admin_client: AsyncClient, admin_client_b: AsyncClient
) -> None:
    """[library/library-guide] 임시 휴관일 / 다른 기관 휴관일 삭제"""
    theirs = (
        await admin_client_b.post("/library/closures", json={"closed_on": "2026-11-20"})
    ).json()
    assert (await admin_client.delete(f"/library/closures/{theirs['id']}")).status_code == 404
    assert [c["id"] for c in (await admin_client_b.get("/library/closures")).json()] == [
        theirs["id"]
    ]
    assert (await admin_client_b.delete(f"/library/closures/{theirs['id']}")).status_code == 204


async def test_closures_by_period(admin_client: AsyncClient, kiosk_client: AsyncClient) -> None:
    for day in ("2026-11-20", "2026-12-24", "2027-03-02"):
        await admin_client.post("/library/closures", json={"closed_on": day})
    default = (await kiosk_client.get("/library/closures")).json()
    assert [c["closed_on"] for c in default] == ["2026-11-20", "2026-12-24"]
    ranged = (await kiosk_client.get("/library/closures?from=2026-12-01&to=2027-12-31")).json()
    assert [c["closed_on"] for c in ranged] == ["2026-12-24", "2027-03-02"]


async def test_next_seven_days(admin_client: AsyncClient, kiosk_client: AsyncClient) -> None:
    """[library/library-guide] 안내 조회 / 앞으로 7일"""
    await admin_client.put("/library/guide", json=GUIDE)
    body = (await kiosk_client.get("/library/guide")).json()
    days = body["next_days"]
    assert [d["date"] for d in days] == [f"2026-11-{n}" for n in range(11, 18)]
    monday = days[5]
    assert (monday["label"], monday["status"], monday["closed_reason"]) == (
        "11월 16일 월요일",
        "closed",
        "정기 휴관",
    )
    for day in days:
        assert (day["due_if_borrowed"] is None) == (day["status"] == "closed")
    assert body["today"]["label"] == "11월 11일 수요일"
    assert body["today"]["due_if_borrowed"]["label"] == "11월 25일 수요일"


async def test_other_library_guide(
    admin_client: AsyncClient,
    admin_client_b: AsyncClient,
    kiosk_client: AsyncClient,
    library_b: Tenant,
) -> None:
    """[library/library-guide] 안내 조회 / 다른 기관의 안내"""
    await admin_client.put("/library/guide", json=GUIDE)
    await admin_client_b.put("/library/guide", json={"contact_phone": "02-111-2222"})
    body = (await kiosk_client.get("/library/guide")).json()
    assert body["contact_phone"] == "031-000-0000"
    assert "02-111-2222" not in str(body)


async def test_kiosk_reads_guide(kiosk_client: AsyncClient) -> None:
    """[library/staff-auth] 역할별 접근 제한 / 키오스크의 안내 조회"""
    assert (await kiosk_client.get("/library/guide")).status_code == 200
    assert (await kiosk_client.get("/library/closures")).status_code == 200


async def test_kiosk_cannot_manage_closures(
    kiosk_client: AsyncClient, admin_client: AsyncClient
) -> None:
    """[library/staff-auth] 역할별 접근 제한 / 키오스크의 휴관일 관리"""
    mine = (await admin_client.post("/library/closures", json={"closed_on": "2026-11-20"})).json()
    assert (
        await kiosk_client.post("/library/closures", json={"closed_on": "2026-11-21"})
    ).status_code == 403
    assert (await kiosk_client.delete(f"/library/closures/{mine['id']}")).status_code == 403
    assert [c["closed_on"] for c in (await admin_client.get("/library/closures")).json()] == [
        "2026-11-20"
    ]
