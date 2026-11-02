"""supply 시드: 유형이 서로 다른 기관 3곳."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.supply import Institution, InstitutionType

INSTITUTIONS = [
    {
        "name": "한빛초등학교",
        "type": InstitutionType.SCHOOL,
        "contact_name": "도서관 담당 교사",
        "phone": "02-000-0001",
    },
    {
        "name": "햇살어린이집",
        "type": InstitutionType.DAYCARE,
        "contact_name": "원장",
        "phone": "02-000-0002",
    },
    {
        "name": "새솔동 행정복지센터",
        "type": InstitutionType.COMMUNITY_CENTER,
        "contact_name": "작은도서관 담당",
        "phone": "02-000-0003",
    },
]


async def seed_supply(session: AsyncSession) -> dict[str, tuple[int, int]]:
    """같은 이름의 기관이 있으면 건너뛴다. {테이블: (생성, 건너뜀)}을 돌려준다."""
    names = [i["name"] for i in INSTITUTIONS]
    existing = set(
        await session.scalars(select(Institution.name).where(Institution.name.in_(names)))
    )
    new = [Institution(**i) for i in INSTITUTIONS if i["name"] not in existing]
    session.add_all(new)
    await session.flush()
    return {"institutions": (len(new), len(INSTITUTIONS) - len(new))}
