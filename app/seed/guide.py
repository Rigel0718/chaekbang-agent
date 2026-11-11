"""도서관 안내 시드. 자체 대출 기관에만 만들고, 가져오기 기관은 처음 쓰는 기관처럼 비워 둔다.

연락처와 시설은 가상이다. 이미 안내가 있으면 건너뛴다. 임시 휴관일은 시드를 실행한 날 기준으로
열흘 뒤에 하나 둔다(앞으로 7일 일정에는 나오지 않고 휴관일 목록에는 나온다).
"""

from datetime import date, time, timedelta

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.library.models.guide import (
    GuideEntry,
    GuideEntryKind,
    LibraryClosure,
    LibraryGuide,
    OpeningHours,
)
from app.seed.library import SUNNY

CONTACT_PHONE = "031-000-1234"  # 가상의 기관 대표 번호
HOURS = [
    *((d, time(9), time(12)) for d in range(1, 5)),  # 화–금 오전
    *((d, time(13), time(18)) for d in range(1, 5)),  # 화–금 오후 (12–13시 점심시간)
    (5, time(9), time(13)),  # 토요일. 일·월요일은 정기 휴관
]
ENTRIES = [
    (GuideEntryKind.FACILITY, "화장실", "1층 출입문 오른쪽에 있어요."),
    (GuideEntryKind.FACILITY, "어린이 자료실", "2층 계단 옆이에요. 신발을 벗고 들어가요."),
    (GuideEntryKind.FACILITY, "열람실", "1층 안쪽이에요. 조용히 이용해 주세요."),
    (GuideEntryKind.RULE, "음식물", "열람실에서는 물 말고는 먹을 수 없어요."),
    (GuideEntryKind.NOTICE, "반납함", "휴관일에는 출입문 옆 무인 반납함에 넣어 주세요."),
]
CLOSURE_AFTER_DAYS = 10


async def seed_guide(
    session: AsyncSession, library_ids: dict[str, int], today: date
) -> dict[str, tuple[int, int]]:
    library_id = library_ids[SUNNY.key]
    if await session.scalar(select(exists().where(LibraryGuide.library_id == library_id))):
        return {"library_guides": (0, 1)}
    session.add(
        LibraryGuide(
            library_id=library_id,
            contact_phone=CONTACT_PHONE,
            loan_limit=5,
            closed_on_public_holidays=True,
        )
    )
    session.add_all(
        OpeningHours(library_id=library_id, weekday=d, opens_at=a, closes_at=b) for d, a, b in HOURS
    )
    session.add_all(
        GuideEntry(library_id=library_id, kind=kind, title=title, body=body, position=i)
        for i, (kind, title, body) in enumerate(ENTRIES)
    )
    session.add(
        LibraryClosure(
            library_id=library_id,
            closed_on=today + timedelta(days=CLOSURE_AFTER_DAYS),
            reason="서가 정리",
        )
    )
    await session.flush()
    return {"library_guides": (1, 0)}
