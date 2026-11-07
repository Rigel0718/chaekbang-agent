from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.models.library import StaffRole
from app.schemas.common import NonEmpty, PatchModel, ReadModel

Password = Annotated[str, Field(min_length=8, max_length=200)]


class StaffCreate(BaseModel):
    login_id: NonEmpty
    password: Password
    role: StaffRole


class StaffUpdate(PatchModel):
    NOT_NULL_FIELDS = ("role", "is_active", "password")

    role: StaffRole | None = None
    is_active: bool | None = None
    password: Password | None = None


class StaffRead(ReadModel):
    """비밀번호 해시는 응답에 넣지 않는다."""

    id: int
    login_id: str
    role: StaffRole
    is_active: bool
    created_at: datetime
