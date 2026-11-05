from typing import Annotated

from pydantic import Field

from app.models.library import LibraryType, LoanMode
from app.schemas.common import NonEmpty, PatchModel, ReadModel


class LibraryRead(ReadModel):
    id: int
    name: str
    type: LibraryType
    loan_mode: LoanMode
    default_loan_days: int


class LibraryUpdate(PatchModel):
    NOT_NULL_FIELDS = ("name", "loan_mode", "default_loan_days")

    name: NonEmpty | None = None
    loan_mode: LoanMode | None = None
    default_loan_days: Annotated[int, Field(ge=1, strict=True)] | None = None
