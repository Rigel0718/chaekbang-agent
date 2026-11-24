from fastapi import APIRouter, Response, status

from app.library.deps import CurrentMember, CurrentStaff, Session
from app.library.schemas.basket import BasketRead
from app.library.services import basket

router = APIRouter(prefix="/basket", tags=["basket"])


@router.get("", response_model=BasketRead)
async def get_basket(staff: CurrentStaff, member: CurrentMember, session: Session):
    """로그인한 회원이 담은 책. 책 값은 지금 상태로 만들고 회원 값은 없다."""
    return BasketRead(books=await basket.list_books(session, staff.library_id, member.member_id))


@router.put("/{library_book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def add_to_basket(
    library_book_id: int, staff: CurrentStaff, member: CurrentMember, session: Session
):
    """책을 담는다. 이미 담았으면 그대로 204. 회원은 회원 세션이 정한다."""
    await basket.add_book(session, staff.library_id, member.member_id, library_book_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{library_book_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_from_basket(
    library_book_id: int, staff: CurrentStaff, member: CurrentMember, session: Session
):
    await basket.remove_book(session, staff.library_id, member.member_id, library_book_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def clear_basket(staff: CurrentStaff, member: CurrentMember, session: Session):
    await basket.clear(session, staff.library_id, member.member_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
