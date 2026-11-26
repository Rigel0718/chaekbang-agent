"""키오스크의 회원 로그인(휴대폰 번호)과 로그아웃.

비밀번호가 없으니 번호가 없는 회원은 로그인할 수 없고, 번호가 틀렸는지 형식이 틀렸는지 알려
주지 않는다. 받은 번호는 메시지·로그에 남기지 않는다. 세션은 키오스크 세션에 묶고 짧게 끝난다.
"""

from datetime import datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.config import get_settings
from app.core.errors import NotFoundError
from app.core.security import hash_token, new_token
from app.library.models.circulation import Member, MemberSession
from app.library.schemas.circulation import normalize_phone

UNKNOWN_PHONE = "번호를 확인해 주세요."
_KEEP_EXPIRED = timedelta(days=1)  # 끝난 세션 행은 하루 뒤 로그인 때 정리한다


async def login(
    session: AsyncSession, library_id: int, staff_session_id: int, phone: str
) -> tuple[str, datetime]:
    """(회원 토큰 원문, 만료 시각). 없는 번호와 형식이 틀린 번호는 같은 NotFoundError다."""
    try:
        digits = normalize_phone(phone)
    except ValueError:
        digits = None
    if digits is None:
        raise NotFoundError(UNKNOWN_PHONE)
    member_id = await session.scalar(
        select(Member.id).where(Member.library_id == library_id, Member.phone == digits)
    )
    if member_id is None:
        raise NotFoundError(UNKNOWN_PHONE)

    now = clock.now()
    # 한 키오스크 세션에는 로그인이 하나다. 앞 사람의 열린 세션을 끊는다.
    await session.execute(
        update(MemberSession)
        .where(
            MemberSession.library_id == library_id,
            MemberSession.staff_session_id == staff_session_id,
            MemberSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    await session.execute(
        delete(MemberSession).where(
            MemberSession.library_id == library_id,
            MemberSession.expires_at < now - _KEEP_EXPIRED,
        )
    )
    token = new_token()
    expires_at = now + timedelta(minutes=get_settings().member_session_minutes)
    session.add(
        MemberSession(
            library_id=library_id,
            staff_session_id=staff_session_id,
            member_id=member_id,
            token_hash=hash_token(token),
            expires_at=expires_at,
        )
    )
    await session.commit()
    return token, expires_at


async def logout(
    session: AsyncSession, library_id: int, staff_session_id: int, token: str | None
) -> None:
    """이 키오스크 세션의 토큰이면 끊는다. 없거나 모르거나 이미 끝났어도 조용히 끝난다."""
    if not token:
        return
    await session.execute(
        update(MemberSession)
        .where(
            MemberSession.token_hash == hash_token(token),
            MemberSession.library_id == library_id,
            MemberSession.staff_session_id == staff_session_id,
            MemberSession.revoked_at.is_(None),
        )
        .values(revoked_at=clock.now())
    )
    await session.commit()
