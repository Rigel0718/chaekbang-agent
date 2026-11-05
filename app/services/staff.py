"""직원 계정 관리 service."""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.library import StaffRole, StaffUser
from app.schemas.staff import StaffCreate, StaffUpdate
from app.services.auth import revoke_all_sessions
from app.services.errors import ConflictError
from app.services.tenancy import get_owned


async def list_staff(
    session: AsyncSession, library_id: int, *, limit: int, offset: int
) -> tuple[list[StaffUser], int]:
    where = StaffUser.library_id == library_id
    total = await session.scalar(select(func.count()).select_from(StaffUser).where(where))
    rows = await session.scalars(
        select(StaffUser).where(where).order_by(StaffUser.id).limit(limit).offset(offset)
    )
    return list(rows), total or 0


async def create_staff(session: AsyncSession, library_id: int, data: StaffCreate) -> StaffUser:
    duplicate = ConflictError(f"이미 쓰는 로그인 아이디입니다: {data.login_id}")
    if await session.scalar(select(StaffUser.id).where(StaffUser.login_id == data.login_id)):
        raise duplicate
    user = StaffUser(
        library_id=library_id,
        login_id=data.login_id,
        password_hash=hash_password(data.password),
        role=data.role,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise duplicate from exc
    await session.refresh(user)
    return user


async def update_staff(
    session: AsyncSession, library_id: int, actor_id: int, staff_id: int, data: StaffUpdate
) -> StaffUser:
    """직원 계정의 역할·사용 여부·비밀번호를 바꾼다.

    자기 계정을 사용 중지하거나 키오스크로 바꾸면 ConflictError다 (관리자가 없어지는 것을 막는다).

    비밀번호를 바꾸면 그 계정의 기존 토큰을 모두 끊는다.
    """
    user = await get_owned(session, StaffUser, library_id, staff_id, label="직원 계정")
    changes = data.changes()
    if staff_id == actor_id and (
        changes.get("is_active") is False or changes.get("role") == StaffRole.KIOSK
    ):
        raise ConflictError("자기 계정은 사용 중지하거나 키오스크로 바꿀 수 없습니다")

    password = changes.pop("password", None)
    for field, value in changes.items():
        setattr(user, field, value)
    if password is not None:
        user.password_hash = hash_password(password)
        await revoke_all_sessions(session, library_id, staff_id)
    await session.commit()
    await session.refresh(user)
    return user
