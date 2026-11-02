from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field

from app.models.supply import InstitutionType
from app.schemas.common import PatchModel, ReadModel

Name = Annotated[str, Field(min_length=1, max_length=200)]


class InstitutionCreate(BaseModel):
    name: Name
    type: InstitutionType
    contact_name: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    memo: str | None = None


class InstitutionUpdate(PatchModel):
    NOT_NULL_FIELDS = ("name", "type")

    name: Name | None = None
    type: InstitutionType | None = None
    contact_name: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None
    memo: str | None = None


class InstitutionRead(ReadModel):
    id: int
    name: str
    type: InstitutionType
    contact_name: str | None
    phone: str | None
    email: str | None
    address: str | None
    memo: str | None
    created_at: datetime
    updated_at: datetime
