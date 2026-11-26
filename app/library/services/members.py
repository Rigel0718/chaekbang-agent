"""회원 service. 개인정보는 회원번호, 이름, 선택 전화번호만 다룬다(전화번호는 검색에 쓰지 않음)."""

from sqlalchemy import exists, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError
from app.core.tenancy import get_owned
from app.library.models.book_request import BookRequest
from app.library.models.circulation import Loan, Member
from app.library.schemas.circulation import MemberCreate, MemberUpdate

LABEL = "회원"


def _duplicate(member_number: str) -> ConflictError:
    return ConflictError(f"이미 쓰는 회원번호예요: {member_number}")


def _duplicate_phone() -> ConflictError:
    return ConflictError("이미 쓰는 전화번호예요.")  # 받은 번호를 메시지에 넣지 않는다


async def _phone_taken(
    session: AsyncSession, library_id: int, phone: str, *, except_id: int | None = None
) -> bool:
    query = select(Member.id).where(Member.library_id == library_id, Member.phone == phone)
    if except_id is not None:
        query = query.where(Member.id != except_id)
    return await session.scalar(query) is not None


async def create_member(session: AsyncSession, library_id: int, data: MemberCreate) -> Member:
    exists_query = select(Member.id).where(
        Member.library_id == library_id, Member.member_number == data.member_number
    )
    if await session.scalar(exists_query) is not None:
        raise _duplicate(data.member_number)
    if data.phone is not None and await _phone_taken(session, library_id, data.phone):
        raise _duplicate_phone()
    member = Member(library_id=library_id, **data.model_dump())
    session.add(member)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        # 동시 요청으로 같은 번호가 먼저 들어간 경우만 여기까지 온다. 아니면 회원번호 중복이다.
        if data.phone is not None and await _phone_taken(session, library_id, data.phone):
            raise _duplicate_phone() from exc
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
    changes = data.changes()
    phone = changes.get("phone")
    if phone is not None and await _phone_taken(session, library_id, phone, except_id=member.id):
        raise _duplicate_phone()
    for field, value in changes.items():
        setattr(member, field, value)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _duplicate_phone() from exc
    await session.refresh(member)
    return member


async def delete_member(session: AsyncSession, library_id: int, member_id: int) -> None:
    """반납 안 된 대출이 있으면 거부한다. 반납된 기록만 있으면 그 기록의 회원 연결을 끊고 지운다.

    사본과 날짜는 대출 통계를 위해 남기고, 탈퇴한 이용자는 대출 기록에서 알아볼 수 없게 한다.
    희망도서 신청은 상태와 상관없이 남기고 회원 연결만 끊는다(구매 근거).
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
        raise ConflictError("반납하지 않은 책이 있는 회원은 삭제할 수 없어요.")
    await session.execute(
        update(Loan)
        .where(Loan.library_id == library_id, Loan.member_id == member_id)
        .values(member_id=None)
    )
    await session.execute(
        update(BookRequest)
        .where(BookRequest.library_id == library_id, BookRequest.member_id == member_id)
        .values(member_id=None)
    )
    await session.delete(member)
    await session.commit()
