"""회원 service. 개인정보는 회원번호와 이름만 다룬다."""

from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.circulation import Loan, Member
from app.schemas.circulation import MemberCreate, MemberUpdate
from app.services.errors import ConflictError
from app.services.tenancy import get_owned

LABEL = "회원"


def _duplicate(member_number: str) -> ConflictError:
    return ConflictError(f"이미 쓰는 회원번호입니다: {member_number}")


async def create_member(session: AsyncSession, library_id: int, data: MemberCreate) -> Member:
    exists_query = select(Member.id).where(
        Member.library_id == library_id, Member.member_number == data.member_number
    )
    if await session.scalar(exists_query) is not None:
        raise _duplicate(data.member_number)
    member = Member(library_id=library_id, **data.model_dump())
    session.add(member)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _duplicate(data.member_number) from exc
    await session.refresh(member)
    return member


async def get_member(session: AsyncSession, library_id: int, member_id: int) -> Member:
    return await get_owned(session, Member, library_id, member_id, label=LABEL)


async def list_members(
    session: AsyncSession, library_id: int, *, limit: int, offset: int, q: str | None = None
) -> tuple[list[Member], int]:
    """q가 있으면 이름이나 회원번호에 q가 들어간 회원만."""
    where = [Member.library_id == library_id]
    if q:
        pattern = f"%{q}%"
        where.append(or_(Member.name.ilike(pattern), Member.member_number.ilike(pattern)))
    total = await session.scalar(select(func.count()).select_from(Member).where(*where))
    rows = await session.scalars(
        select(Member).where(*where).order_by(Member.member_number).limit(limit).offset(offset)
    )
    return list(rows), total or 0


async def update_member(
    session: AsyncSession, library_id: int, member_id: int, data: MemberUpdate
) -> Member:
    member = await get_member(session, library_id, member_id)
    for field, value in data.changes().items():
        setattr(member, field, value)
    await session.commit()
    await session.refresh(member)
    return member


async def delete_member(session: AsyncSession, library_id: int, member_id: int) -> None:
    """반납 안 된 대출이 있으면 거부한다. 반납된 기록만 있으면 그 기록의 회원 연결을 끊고 지운다.

    사본과 날짜는 대출 통계를 위해 남기고, 탈퇴한 이용자는 대출 기록에서 알아볼 수 없게 한다.
    """
    member = await get_member(session, library_id, member_id)
    has_active = await session.scalar(
        select(
            exists().where(
                Loan.library_id == library_id,
                Loan.member_id == member_id,
                Loan.returned_on.is_(None),
            )
        )
    )
    if has_active:
        raise ConflictError("반납하지 않은 대출이 있는 회원은 삭제할 수 없습니다")
    await session.execute(
        update(Loan)
        .where(Loan.library_id == library_id, Loan.member_id == member_id)
        .values(member_id=None)
    )
    await session.delete(member)
    await session.commit()
