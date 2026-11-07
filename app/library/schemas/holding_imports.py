from datetime import datetime
from typing import Any

from app.core.schemas import ReadModel
from app.library.models.catalog import ImportStatus


class HoldingImportRead(ReadModel):
    id: int
    filename: str
    status: ImportStatus
    column_mapping: dict[str, Any]
    summary: dict[str, Any]
    created_at: datetime
    applied_at: datetime | None


class HoldingImportRow(ReadModel):
    row_no: int
    outcome: str
    skip_reason: str | None
    flags: list[str]
    accession_number: str | None
    title: str | None
    author: str | None
    isbn: str | None
    status: str | None
    acquisition: str | None
