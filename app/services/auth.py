"""로그인·로그아웃과 내 정보."""

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import get_settings
from app.core.security import hash_token, new_token, verify_dummy, verify_password
from app.models.library import Library, StaffRole, StaffSession, StaffUser
from app.services.errors import AuthenticationError

INVALID_LOGIN = "아이디 또는 비밀번호가 올바르지 않습니다"


def token_lifetime(role: StaffRole) -> timedelta:
    settings = get_settings()
    hours = settings.admin_token_hours if role == StaffRole.ADMIN else settings.kiosk_token_hours
    return timedelta(hours=hours)


async def login(
    session: AsyncSession, login_id: str, password: str
) -> tuple[str, StaffUser, datetime]:
    """(토큰 원문, 계정, 만료 시각). 실패 사유와 상관없이 같은 메시지의 AuthenticationError."""
    user = await session.scalar(select(StaffUser).where(StaffUser.login_id == login_id))
    if user is None:
        verify_dummy(password)
        raise AuthenticationError(INVALID_LOGIN)
    if not verify_password(password, user.password_hash) or not user.is_active:
        raise AuthenticationError(INVALID_LOGIN)

    token = new_token()
    expires_at = clock.now() + token_lifetime(user.role)
    session.add(
        StaffSession(
            library_id=user.library_id,
            staff_user_id=user.id,
            token_hash=hash_token(token),
            expires_at=expires_at,
        )
    )
    await session.commit()
    return token, user, expires_at


async def logout(session: AsyncSession, session_id: int) -> None:
    await session.execute(
        update(StaffSession)
        .where(StaffSession.id == session_id, StaffSession.revoked_at.is_(None))
        .values(revoked_at=clock.now())
    )
    await session.commit()


async def revoke_all_sessions(session: AsyncSession, library_id: int, staff_id: int) -> None:
    """계정의 열린 세션을 모두 끊는다 (비밀번호 변경 시). 커밋은 호출한 쪽이 한다."""
    await session.execute(
        update(StaffSession)
        .where(
            StaffSession.library_id == library_id,
            StaffSession.staff_user_id == staff_id,
            StaffSession.revoked_at.is_(None),
        )
        .values(revoked_at=clock.now())
    )


async def me(session: AsyncSession, library_id: int, staff_id: int) -> tuple[StaffUser, Library]:
    row = (
        await session.execute(
            select(StaffUser, Library)
            .join(Library, Library.id == StaffUser.library_id)
            .where(StaffUser.id == staff_id, StaffUser.library_id == library_id)
        )
    ).one()
    return row[0], row[1]
