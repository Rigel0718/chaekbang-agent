"""도서관 안내 API. 키오스크는 읽고, 관리자는 바꾼다.

화면의 "도서관 안내" 칸은 LLM 없이 이 API로 그린다.
"""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.library.deps import AdminStaff, CurrentStaff, Session
from app.library.schemas.guide import ClosureCreate, ClosureRead, GuideRead, GuideUpdate
from app.library.services import guide

router = APIRouter(prefix="/library", tags=["library-guide"])


@router.get("/guide", response_model=GuideRead)
async def get_guide(staff: CurrentStaff, session: Session):
    """등록된 안내와 코드가 계산한 오늘·앞으로 7일의 개관 여부, 그날 빌리면 반납 예정일.

    안내를 등록하지 않은 기관도 200이고 `registered`가 false다.
    """
    return await guide.get_guide(session, staff.library_id)


@router.put("/guide", response_model=GuideRead)
async def replace_guide(data: GuideUpdate, staff: AdminStaff, session: Session):
    """안내 전체를 바꾼다. 보내지 않은 운영 시간과 자유 항목은 지워진다.

    대표 연락처에는 기관 대표 번호만 넣는다. 담당자·자원봉사자의 개인 번호를 넣지 않는다.
    """
    return await guide.replace_guide(session, staff.library_id, data)


@router.get("/closures", response_model=list[ClosureRead])
async def list_closures(
    staff: CurrentStaff,
    session: Session,
    start: Annotated[date | None, Query(alias="from", description="기본: 오늘")] = None,
    end: Annotated[date | None, Query(alias="to", description="기본: 시작일부터 90일")] = None,
):
    return await guide.list_closures(session, staff.library_id, start, end)


@router.post("/closures", status_code=status.HTTP_201_CREATED, response_model=ClosureRead)
async def add_closure(data: ClosureCreate, staff: AdminStaff, session: Session):
    """임시 휴관일. 정부가 갑자기 정한 임시공휴일에 쉬는 경우도 여기에 등록한다."""
    return await guide.add_closure(session, staff.library_id, data)


@router.delete("/closures/{closure_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_closure(closure_id: int, staff: AdminStaff, session: Session):
    await guide.delete_closure(session, staff.library_id, closure_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
