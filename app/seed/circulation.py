"""회원(기관마다 10명)과 대출(자체 대출 기관만) 시드.

대출 날짜는 시드를 실행한 날 기준으로 만든다. 연체 대출이 항상 연체로 보이게 하기 위해서다.
"""

import random
from datetime import date, timedelta

from faker import Faker
from sqlalchemy import exists, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.library.models.catalog import Holding, HoldingStatus
from app.library.models.circulation import Loan, Member
from app.seed.library import LIBRARIES, SUNNY

MEMBERS_PER_LIBRARY = 10
RETURNED, ACTIVE, OVERDUE = 5, 5, 3


async def seed_members(
    session: AsyncSession, seed: int, library_ids: dict[str, int]
) -> dict[str, tuple[int, int]]:
    fake = Faker("ko_KR")
    fake.seed_instance(seed + 100)
    rows = [
        {"library_id": library_ids[lib.key], "member_number": f"M{n:04d}", "name": fake.name()}
        for lib in LIBRARIES
        for n in range(1, MEMBERS_PER_LIBRARY + 1)
    ]
    result = await session.execute(
        insert(Member)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["library_id", "member_number"])
        .returning(Member.id)
    )
    created = len(result.all())
    return {"members": (created, len(rows) - created)}


async def seed_loans(
    session: AsyncSession, seed: int, library_ids: dict[str, int], today: date
) -> dict[str, tuple[int, int]]:
    """자체 대출 기관에 대출이 하나도 없을 때만 만든다: 반납 5, 대출 중 5, 연체 3."""
    library_id = library_ids[SUNNY.key]
    if await session.scalar(select(exists().where(Loan.library_id == library_id))):
        return {"loans": (0, RETURNED + ACTIVE + OVERDUE)}

    rng = random.Random(seed + 200)
    holdings = list(
        await session.scalars(
            select(Holding.id)
            .where(Holding.library_id == library_id, Holding.status == HoldingStatus.AVAILABLE)
            .order_by(Holding.accession_number)
        )
    )
    members = list(
        await session.scalars(
            select(Member.id).where(Member.library_id == library_id).order_by(Member.member_number)
        )
    )
    picked = rng.sample(holdings, RETURNED + ACTIVE + OVERDUE)
    returned, active, overdue = (
        picked[:RETURNED],
        picked[RETURNED : RETURNED + ACTIVE],
        picked[RETURNED + ACTIVE :],
    )
    days = SUNNY.default_loan_days

    rows = []
    for holding_id in returned:
        loaned = today - timedelta(days=rng.randrange(20, 60))
        rows.append(
            (
                holding_id,
                loaned,
                loaned + timedelta(days=days),
                loaned + timedelta(days=rng.randrange(3, days)),
            )
        )
    for holding_id in active:
        loaned = today - timedelta(days=rng.randrange(0, days - 1))
        rows.append((holding_id, loaned, loaned + timedelta(days=days), None))
    for holding_id in overdue:
        loaned = today - timedelta(days=rng.randrange(days + 2, days + 20))
        rows.append((holding_id, loaned, loaned + timedelta(days=days), None))

    await session.execute(
        insert(Loan).values(
            [
                {
                    "library_id": library_id,
                    "holding_id": holding_id,
                    "member_id": rng.choice(members),
                    "loaned_on": loaned,
                    "due_on": due,
                    "returned_on": returned_on,
                }
                for holding_id, loaned, due, returned_on in rows
            ]
        )
    )
    await session.execute(
        update(Holding).where(Holding.id.in_(active + overdue)).values(status=HoldingStatus.ON_LOAN)
    )
    return {"loans": (len(rows), 0)}
