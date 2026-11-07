import json
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from pydantic import TypeAdapter, ValidationError

from app.core.schemas import Page, Pagination, page_of
from app.library.deps import AdminStaff, Session
from app.library.importing.reader import MAX_BYTES
from app.library.schemas.holding_imports import HoldingImportRead, HoldingImportRow
from app.library.services import holding_imports
from app.library.services.holding_imports import Outcome

router = APIRouter(prefix="/holding-imports", tags=["holding-imports"])

_Mapping = TypeAdapter(dict[str, str])


def _overrides(raw: str | None) -> dict[str, str] | None:
    if not raw:
        return None
    try:
        return _Mapping.validate_python(json.loads(raw))
    except (ValueError, ValidationError) as exc:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            'column_mapping은 {"author": "책임표시"} 형식의 JSON이어야 합니다',
        ) from exc


@router.post("", status_code=status.HTTP_201_CREATED, response_model=HoldingImportRead)
async def create_import(
    staff: AdminStaff,
    session: Session,
    file: Annotated[UploadFile, File(description="대출 프로그램의 xlsx·CSV 내보내기")],
    column_mapping: Annotated[
        str | None, Form(description='자동 인식보다 우선할 열. 예: {"author": "책임표시"}')
    ] = None,
):
    """미리 보기를 만든다. 장서는 적용하기 전까지 바뀌지 않는다."""
    content = await file.read(MAX_BYTES + 1)
    return await holding_imports.create_preview(
        session,
        staff.library_id,
        staff.staff_id,
        file.filename or "upload",
        content,
        _overrides(column_mapping),
    )


@router.get("", response_model=Page[HoldingImportRead])
async def list_imports(staff: AdminStaff, session: Session, page: Annotated[Pagination, Query()]):
    rows, total = await holding_imports.list_imports(
        session, staff.library_id, limit=page.limit, offset=page.offset
    )
    return page_of(HoldingImportRead, rows, total, page)


@router.get("/{import_id}", response_model=HoldingImportRead)
async def get_import(import_id: int, staff: AdminStaff, session: Session):
    return await holding_imports.get_import(session, staff.library_id, import_id)


@router.get("/{import_id}/rows", response_model=Page[HoldingImportRow])
async def list_rows(
    import_id: int,
    staff: AdminStaff,
    session: Session,
    page: Annotated[Pagination, Query()],
    outcome: Outcome | None = None,
    flag: str | None = None,
):
    rows, total = await holding_imports.list_rows(
        session,
        staff.library_id,
        import_id,
        limit=page.limit,
        offset=page.offset,
        outcome=outcome,
        flag=flag,
    )
    return page_of(HoldingImportRow, rows, total, page)


@router.post("/{import_id}/apply", response_model=HoldingImportRead)
async def apply_import(
    import_id: int,
    staff: AdminStaff,
    session: Session,
    confirm_withdraw: Annotated[
        bool, Query(description="빠진 사본이 절반 이상일 때 true로 확인한다")
    ] = False,
):
    return await holding_imports.apply_import(
        session, staff.library_id, import_id, confirm_withdraw=confirm_withdraw
    )
