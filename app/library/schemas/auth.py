from datetime import datetime

from pydantic import BaseModel, Field

from app.library.models.library import StaffRole


class LoginRequest(BaseModel):
    login_id: str
    password: str


class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    role: StaffRole
    expires_at: datetime


class MemberLoginRequest(BaseModel):
    phone: str = Field(max_length=30)


class MemberLoginResponse(BaseModel):
    """회원 토큰과 만료 시각뿐이다. 회원번호·이름·전화번호를 돌려주지 않는다."""

    member_token: str
    expires_at: datetime


class MeResponse(BaseModel):
    staff_id: int
    login_id: str
    role: StaffRole
    library_id: int
    library_name: str
