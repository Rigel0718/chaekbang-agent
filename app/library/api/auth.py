from fastapi import APIRouter, status

from app.core.deps import CurrentStaff, Session
from app.schemas.auth import LoginRequest, LoginResponse, MeResponse
from app.services import auth

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
