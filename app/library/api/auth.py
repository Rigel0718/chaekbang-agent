from fastapi import APIRouter, status

from app.library.deps import CurrentStaff, MemberToken, Session
from app.library.schemas.auth import (
    LoginRequest,
    LoginResponse,
    MemberLoginRequest,
    MemberLoginResponse,
    MeResponse,
)
from app.library.services import auth, member_auth

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(data: LoginRequest, session: Session):
    token, user, expires_at = await auth.login(session, data.login_id, data.password)
    return LoginResponse(token=token, role=user.role, expires_at=expires_at)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(staff: CurrentStaff, session: Session) -> None:
    await auth.logout(session, staff.session_id)


@router.get("/me", response_model=MeResponse)
async def me(staff: CurrentStaff, session: Session):
    user, library = await auth.me(session, staff.library_id, staff.staff_id)
    return MeResponse(
        staff_id=user.id,
        login_id=user.login_id,
        role=user.role,
        library_id=library.id,
        library_name=library.name,
    )


@router.post("/member-login", response_model=MemberLoginResponse)
async def member_login(data: MemberLoginRequest, staff: CurrentStaff, session: Session):
    """휴대폰 번호로 회원 로그인한다. 키오스크와 관리자가 쓴다. 응답에 회원 값은 없다."""
    token, expires_at = await member_auth.login(
        session, staff.library_id, staff.session_id, data.phone
    )
    return MemberLoginResponse(member_token=token, expires_at=expires_at)


@router.post("/member-logout", status_code=status.HTTP_204_NO_CONTENT)
async def member_logout(staff: CurrentStaff, token: MemberToken, session: Session) -> None:
    """`X-Member-Token`의 회원 세션을 끊는다. 이미 끝났거나 모르는 토큰이어도 204다."""
    await member_auth.logout(session, staff.library_id, staff.session_id, token)
