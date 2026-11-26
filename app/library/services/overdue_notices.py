"""연체 안내 service: 안내문 틀(승인 흐름), 연체 줄, 연체 안내 목록.

관리 REST(`api/overdue_notices.py`)와 운영 에이전트의 두 tool(`overdue_tools.py`)이 이 함수들을
부른다. 승인은 틀에만 받는다. 승인하면 같은 트랜잭션에서 확정하고(`CONFIRMING`), 그 기관이 쓰는
틀은 확정된 틀 가운데 가장 늦게 확정된 하나다. 연체 안내 목록은 요청할 때마다 지금의 연체 대출과
쓰는 틀로 계산하고 저장하지 않는다. 회원 값은 이 service 밖(LLM)으로 나가지 않는다: tool은
`OverdueLoan`에서 회원 칸을 빼고 쓴다.

외부 대출 기관은 이 시스템에 대출 기록이 없어 모든 함수가 409로 막는다.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.models import Book
from app.core import clock
from app.core.errors import ConflictError, InvalidRequestError
from app.core.tenancy import get_owned
from app.library import overdue_template as tpl
from app.library.approval import (
    CONFIRMING,
    Action,
    ApprovalStatus,
    mark_executed,
    require_status,
    transition,
)
from app.library.models.catalog import Holding, LibraryBook
from app.library.models.circulation import Loan, Member
from app.library.models.library import Library, LoanMode
from app.library.models.overdue_notice import OverdueNoticeTemplate
from app.library.privacy import mask_personal
from app.library.schemas.overdue_notice import NoticeLine, NoticeList, TemplateWrite

LABEL = "연체 안내 양식"
EXTERNAL_LOANS = "이 도서관의 대출은 기존 대출 프로그램에서 관리해서 연체 안내를 만들 수 없어요."
NO_TEMPLATE = "승인한 연체 안내 양식이 없어요."
PERSONAL_IN_BODY = (
    "양식에 전화번호·이메일·회원번호 같은 개인정보가 있어요. 회원 값은 자리표시로만 써 주세요."
)


@dataclass(frozen=True)
class OverdueLoan:
    """연체 대출 한 건. 회원 칸은 관리자용 목록에만 쓰고 LLM에 보내는 tool은 쓰지 않는다."""

    loan_id: int
    title: str
    accession_number: str
    due_on: date
    overdue_days: int
    member_number: str
    name: str
    phone: str | None


async def _library(session: AsyncSession, library_id: int) -> Library:
    """대출을 이 시스템에서 하는 기관만 통과시킨다. 외부 대출 기관은 409."""
    library = await session.get(Library, library_id)
    assert library is not None
    if library.loan_mode == LoanMode.EXTERNAL:
        raise ConflictError(EXTERNAL_LOANS)
    return library


async def _check_body(session: AsyncSession, library_id: int, data: TemplateWrite) -> None:
    """개인정보 형태가 든 틀은 몰래 가리지 않고 거부한다. 메시지에 찾은 값을 담지 않는다."""
    if await mask_personal(session, library_id, data.body) != data.body:
        raise InvalidRequestError(PERSONAL_IN_BODY)


async def get_template(
    session: AsyncSession, library_id: int, template_id: int
) -> OverdueNoticeTemplate:
    await _library(session, library_id)
    return await get_owned(session, OverdueNoticeTemplate, library_id, template_id, label=LABEL)


async def _reload(
    session: AsyncSession, library_id: int, template_id: int
) -> OverdueNoticeTemplate:
    """Core UPDATE로 바뀐 상태를 ORM 객체에 다시 읽는다."""
    row = await session.scalar(
        select(OverdueNoticeTemplate)
        .where(
            OverdueNoticeTemplate.id == template_id, OverdueNoticeTemplate.library_id == library_id
        )
        .execution_options(populate_existing=True)
    )
    assert row is not None
    return row


async def create_template(
    session: AsyncSession,
    library_id: int,
    staff_id: int | None,
    data: TemplateWrite,
    *,
    submit: bool = False,
) -> OverdueNoticeTemplate:
    """초안을 만든다. `submit`이면 같은 트랜잭션에서 승인 대기로 올린다(운영 에이전트 tool)."""
    await _library(session, library_id)
    await _check_body(session, library_id, data)
    template = OverdueNoticeTemplate(library_id=library_id, body=data.body, created_by=staff_id)
    session.add(template)
    await session.flush()
    if submit:
        await transition(
            session,
            OverdueNoticeTemplate,
            CONFIRMING,
            library_id,
            template.id,
            Action.SUBMIT,
            label=LABEL,
        )
    await session.commit()
    return await _reload(session, library_id, template.id)


async def update_template(
    session: AsyncSession, library_id: int, template_id: int, data: TemplateWrite
) -> OverdueNoticeTemplate:
    """초안의 문장을 바꾼다. 초안이 아니면 409."""
    template = await get_template(session, library_id, template_id)
    require_status(template, ApprovalStatus.DRAFT, label=LABEL, doing="고칠")
    await _check_body(session, library_id, data)
    template.body = data.body
    await session.commit()
    return await _reload(session, library_id, template_id)


async def delete_template(session: AsyncSession, library_id: int, template_id: int) -> None:
    template = await get_template(session, library_id, template_id)
    require_status(template, ApprovalStatus.DRAFT, label=LABEL, doing="지울")
    await session.delete(template)
    await session.commit()


async def submit_template(
    session: AsyncSession, library_id: int, template_id: int
) -> OverdueNoticeTemplate:
    await _library(session, library_id)
    await transition(
        session,
        OverdueNoticeTemplate,
        CONFIRMING,
        library_id,
        template_id,
        Action.SUBMIT,
        label=LABEL,
    )
    await session.commit()
    return await _reload(session, library_id, template_id)


async def approve_template(
    session: AsyncSession, library_id: int, template_id: int, staff_id: int | None
) -> OverdueNoticeTemplate:
    """승인하고 같은 트랜잭션에서 확정한다. 확정은 상태를 바꾸는 것뿐이라 실패할 일이 없다."""
    await _library(session, library_id)
    now = clock.now()
    await transition(
        session,
        OverdueNoticeTemplate,
        CONFIRMING,
        library_id,
        template_id,
        Action.APPROVE,
        label=LABEL,
        values={"approved_by": staff_id, "approved_at": now, "rejected_reason": None},
    )
    await mark_executed(session, OverdueNoticeTemplate, CONFIRMING, library_id, template_id, now)
    await session.commit()
    return await _reload(session, library_id, template_id)


async def reject_template(
    session: AsyncSession, library_id: int, template_id: int, reason: str
) -> OverdueNoticeTemplate:
    await _library(session, library_id)
    await transition(
        session,
        OverdueNoticeTemplate,
        CONFIRMING,
        library_id,
        template_id,
        Action.REJECT,
        label=LABEL,
        values={"rejected_reason": reason},
    )
    await session.commit()
    return await _reload(session, library_id, template_id)


async def list_templates(
    session: AsyncSession, library_id: int, status: ApprovalStatus | None = None
) -> list[OverdueNoticeTemplate]:
    await _library(session, library_id)
    query = select(OverdueNoticeTemplate).where(OverdueNoticeTemplate.library_id == library_id)
    if status is not None:
        query = query.where(OverdueNoticeTemplate.status == status)
    rows = await session.scalars(
        query.order_by(OverdueNoticeTemplate.created_at.desc(), OverdueNoticeTemplate.id.desc())
    )
    return list(rows)


async def current_template(session: AsyncSession, library_id: int) -> OverdueNoticeTemplate | None:
    """그 기관이 쓰는 틀: 확정된 틀 가운데 확정 시각이 가장 늦은 것(같으면 id가 큰 것)."""
    return await session.scalar(
        select(OverdueNoticeTemplate)
        .where(
            OverdueNoticeTemplate.library_id == library_id,
            OverdueNoticeTemplate.status == ApprovalStatus.CONFIRMED,
        )
        .order_by(OverdueNoticeTemplate.executed_at.desc(), OverdueNoticeTemplate.id.desc())
        .limit(1)
    )


async def overdue_loans(
    session: AsyncSession, library_id: int, today: date | None = None
) -> list[OverdueLoan]:
    """연체 대출을 회원번호, 반납 예정일, 대출 id 순으로 돌려준다(`services/loans.py`와 같은 조건).

    서명은 공식 서지를 먼저 쓴다. 미반납 대출은 저장 계층이 회원을 요구하므로 회원은 늘 있다.
    """
    await _library(session, library_id)
    today = today or clock.today()
    rows = await session.execute(
        select(
            Loan.id,
            Loan.due_on,
            Holding.accession_number,
            LibraryBook.title.label("own_title"),
            Book.title.label("official_title"),
            Member.member_number,
            Member.name,
            Member.phone,
        )
        .join(
            Holding,
            and_(Holding.library_id == Loan.library_id, Holding.id == Loan.holding_id),
        )
        .join(
            LibraryBook,
            and_(
                LibraryBook.library_id == Holding.library_id,
                LibraryBook.id == Holding.library_book_id,
            ),
        )
        .outerjoin(Book, Book.id == LibraryBook.book_id)
        .join(Member, and_(Member.library_id == Loan.library_id, Member.id == Loan.member_id))
        .where(Loan.library_id == library_id, Loan.returned_on.is_(None), Loan.due_on < today)
        .order_by(Member.member_number, Loan.due_on, Loan.id)
    )
    return [
        OverdueLoan(
            loan_id=row.id,
            title=row.official_title if row.official_title is not None else row.own_title,
            accession_number=row.accession_number,
            due_on=row.due_on,
            overdue_days=(today - row.due_on).days,
            member_number=row.member_number,
            name=row.name,
            phone=row.phone,
        )
        for row in rows
    ]


def fill_message(body: str, loan: OverdueLoan, library_name: str) -> str:
    """틀의 자리표시를 이 대출의 값으로 채운다. 회원 이름은 여기서만 문장에 들어간다."""
    return tpl.fill(
        body,
        {
            tpl.NAME: loan.name,
            tpl.TITLE: loan.title,
            tpl.DUE_DATE: loan.due_on.isoformat(),
            tpl.OVERDUE_DAYS: str(loan.overdue_days),
            tpl.LIBRARY: library_name,
        },
    )


async def notice_list(session: AsyncSession, library_id: int) -> NoticeList:
    """지금의 연체 대출마다 쓰는 틀로 채운 문안. 확정된 틀이 없으면 409. 저장하지 않는다."""
    library = await _library(session, library_id)
    template = await current_template(session, library_id)
    if template is None:
        raise ConflictError(NO_TEMPLATE)
    today = clock.today()
    loans = await overdue_loans(session, library_id, today)
    return NoticeList(
        today=today,
        template_id=template.id,
        total=len(loans),
        lines=[
            NoticeLine(
                member_number=loan.member_number,
                name=loan.name,
                phone=loan.phone,
                title=loan.title,
                accession_number=loan.accession_number,
                due_on=loan.due_on,
                overdue_days=loan.overdue_days,
                message=fill_message(template.body, loan, library.name),
            )
            for loan in loans
        ],
    )
