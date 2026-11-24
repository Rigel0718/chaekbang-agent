"""인증 의존성: 토큰 → 현재 직원과 기관, 역할 검사.

401·403은 인증 계층(HTTP)의 관심사라 여기서 HTTPException으로 올린다. service는 HTTP를 모른다.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.db import get_session
from app.core.security import hash_token
from app.library.models.circulation import MemberSession
from app.library.models.library import StaffRole, StaffSession, StaffUser

Session = Annotated[AsyncSession, Depends(get_session)]

_bearer = HTTPBearer(auto_error=False, description="POST /auth/login으로 받은 토큰")


@dataclass(frozen=True)
class StaffContext:
    staff_id: int
    library_id: int
    role: StaffRole
    session_id: int

    @property
    def is_admin(self) -> bool:
        return self.role == StaffRole.ADMIN


MEMBER_REQUIRED = "회원 로그인이 필요합니다"


def _unauthorized() -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED,
        "로그인이 필요합니다",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def current_staff(
    session: Session,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> StaffContext:
    """유효한 세션(로그아웃 안 함, 만료 안 됨)과 사용 중인 계정일 때만 통과한다.

    역할은 토큰이 아니라 요청마다 계정에서 읽는다. 역할 변경이 바로 반영된다.
    """
    if credentials is None:
        raise _unauthorized()
    row = (
        await session.execute(
            select(StaffSession.id, StaffUser.id, StaffUser.library_id, StaffUser.role)
            .join(
                StaffUser,
                (StaffUser.id == StaffSession.staff_user_id)
                & (StaffUser.library_id == StaffSession.library_id),
            )
            .where(
                StaffSession.token_hash == hash_token(credentials.credentials),
                StaffSession.revoked_at.is_(None),
                StaffSession.expires_at > clock.now(),
                StaffUser.is_active.is_(True),
            )
        )
    ).one_or_none()
    if row is None:
        raise _unauthorized()
    session_id, staff_id, library_id, role = row
    return StaffContext(staff_id=staff_id, library_id=library_id, role=role, session_id=session_id)


CurrentStaff = Annotated[StaffContext, Depends(current_staff)]


async def require_admin(staff: CurrentStaff) -> StaffContext:
    if not staff.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "관리자만 할 수 있습니다")
    return staff


AdminStaff = Annotated[StaffContext, Depends(require_admin)]

_member_header = APIKeyHeader(
    name="X-Member-Token",
    auto_error=False,
    description="POST /auth/member-login으로 받은 회원 토큰",
)
MemberToken = Annotated[str | None, Depends(_member_header)]


@dataclass(frozen=True)
class MemberContext:
    member_id: int
    session_id: int


async def current_member(
    staff: CurrentStaff, session: Session, token: MemberToken
) -> MemberContext:
    """회원 세션이 유효할 때만 통과한다. 직원 토큰 오류(401)가 먼저, 회원 세션 오류는 403이다.

    세션은 로그아웃·만료 전이고, 이 키오스크 세션과 이 기관의 것이어야 한다.
    """
    row = None
    if token:
        row = (
            await session.execute(
                select(MemberSession.id, MemberSession.member_id).where(
                    MemberSession.token_hash == hash_token(token),
                    MemberSession.library_id == staff.library_id,
                    MemberSession.staff_session_id == staff.session_id,
                    MemberSession.revoked_at.is_(None),
                    MemberSession.expires_at > clock.now(),
                )
            )
        ).one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, MEMBER_REQUIRED)
    return MemberContext(member_id=row.member_id, session_id=row.id)


CurrentMember = Annotated[MemberContext, Depends(current_member)]
