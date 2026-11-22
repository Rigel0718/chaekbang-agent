"""희망도서 service. 회원번호는 신청할 때 회원을 찾는 데만 쓰고 저장하는 것은 회원 연결뿐이다.

소장 검사는 ISBN이 있을 때만 한다(서명 비교는 오타 허용이라 애매하다). 같은 회원의 같은 서명
(맞춤 키) 처리 전 신청은 하나만 둔다. 동시 요청은 부분 UNIQUE 인덱스가 막는다.
"""

from sqlalchemy import exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.models import Book
from app.core import clock
from app.core.errors import ConflictError, InvalidRequestError, NotFoundError
from app.core.tenancy import get_owned
from app.core.text import match_key
from app.library.models.book_request import BookRequest, BookRequestStatus
from app.library.models.catalog import LibraryBook
from app.library.models.circulation import Member
from app.library.recommendation.search import recommendable_ids
from app.library.schemas.book_request import BookRequestCreate

LABEL = "희망도서 신청"
UNKNOWN_MEMBER = "회원번호를 확인해 주세요"
ALREADY_REQUESTED = "이미 신청한 책이에요"
ALREADY_HELD = "이미 도서관에 있는 책이에요"


async def _is_held(session: AsyncSession, library_id: int, isbn: str) -> bool:
    """그 ISBN이 그 기관의 추천 가능한 책(공식 서지 ISBN 또는 기관 도서 ISBN)인지."""
    official = select(Book.id).where(Book.isbn == isbn)
    return bool(
        await session.scalar(
            select(
                exists().where(
                    LibraryBook.library_id == library_id,
                    LibraryBook.id.in_(recommendable_ids(library_id)),
                    or_(LibraryBook.isbn == isbn, LibraryBook.book_id.in_(official)),
                )
            )
        )
    )


async def create_request(
    session: AsyncSession, library_id: int, data: BookRequestCreate
) -> BookRequest:
    member = await session.scalar(
        select(Member).where(
            Member.library_id == library_id, Member.member_number == data.member_number
        )
    )
    if member is None:
        raise NotFoundError(UNKNOWN_MEMBER)  # 받은 번호를 메시지에 넣지 않는다
    title_key = match_key(data.title)
    if not title_key:
        raise InvalidRequestError("서명에 글자나 숫자가 있어야 합니다")
    if data.isbn is not None and await _is_held(session, library_id, data.isbn):
        raise ConflictError(ALREADY_HELD)
    duplicate = await session.scalar(
        select(
            exists().where(
                BookRequest.library_id == library_id,
                BookRequest.member_id == member.id,
                BookRequest.title_key == title_key,
                BookRequest.status == BookRequestStatus.REQUESTED,
            )
        )
    )
    if duplicate:
        raise ConflictError(ALREADY_REQUESTED)
    request = BookRequest(
        library_id=library_id,
        member_id=member.id,
        title=data.title,
        title_key=title_key,
        author=data.author,
        isbn=data.isbn,
    )
    session.add(request)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ConflictError(ALREADY_REQUESTED) from exc
    await session.refresh(request)
    return request


async def list_requests(
    session: AsyncSession,
    library_id: int,
    *,
    limit: int,
    offset: int,
    status: BookRequestStatus | None = None,
) -> tuple[list[BookRequest], int]:
    where = [BookRequest.library_id == library_id]
    if status is not None:
        where.append(BookRequest.status == status)
    total = await session.scalar(select(func.count()).select_from(BookRequest).where(*where))
    rows = await session.scalars(
        select(BookRequest)
        .where(*where)
        .order_by(BookRequest.created_at.desc(), BookRequest.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return list(rows.unique()), total or 0


async def close_request(session: AsyncSession, library_id: int, request_id: int) -> BookRequest:
    """처리 전 신청을 닫는다. 이미 닫힌 신청은 그대로 돌려준다."""
    request = await get_owned(session, BookRequest, library_id, request_id, label=LABEL)
    if request.status != BookRequestStatus.CLOSED:
        request.status = BookRequestStatus.CLOSED
        request.closed_at = clock.now()
        await session.commit()
        await session.refresh(request)
    return request
