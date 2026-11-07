from datetime import datetime

from pydantic import BaseModel

from app.library.models.library import StaffRole


class LoginRequest(BaseModel):
    login_id: str
    password: str


class LoginResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    role: StaffRole
    expires_at: datetime


class MeResponse(BaseModel):
    staff_id: int
    login_id: str
    role: StaffRole
    library_id: int
    library_name: str
