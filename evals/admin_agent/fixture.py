"""평가 기관: 코드로 만드는 가상 자체 대출 기관과 외부 대출 기관. 오늘은 2026-11-19로 고정한다.

실험 장서는 대출 기록이 없고 분포를 정할 수 없어 쓰지 않는다. 숫자의 정답은 pytest가 보장하므로
여기서는 질문마다 가려낼 수 있는 분포만 만든다. 서명은 가상이고 회원 이름도 가상이다. 같은 코드로
두 번 만들면 같은 결과가 나온다(id만 다르다).

책 표: (서명, KDC, 어린이, 사본 상태들, 입수, 등록, 대출 날짜들). 대출 날짜 뒤의 `!`는 반납하지 않은
대출이고, `?`는 반납하지 않았고 반납 예정일이 지난 대출(연체)이다.

구매 요청서 평가(`add-purchase-request`)를 위해 책마다 가상 ISBN(`eval_isbn`)을 주고, 희망도서
신청과 승인 대기 구매 요청서를 둔다. 분석 결과에는 ISBN과 희망도서가 들어가지 않아 분석 라벨의
숫자는 그대로다(`tests/evals/test_admin_agent_eval.py`가 확인한다).
"""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import clock
from app.core.contributors import author_keys
from app.core.isbn import isbn13_check_digit
from app.core.text import match_key

TODAY = date(2026, 11, 19)
NOW = datetime(2026, 11, 19, 5, 0, tzinfo=UTC)  # 기관 시간대 14:00
REGISTERED = datetime(2025, 6, 1, tzinfo=UTC)
NEW = datetime(2026, 11, 5, tzinfo=UTC)

A, D, U = "purchased", "donated", "unknown"

# 서명, KDC(None이면 분류 없음, `청:`이면 청구기호로만), 어린이, 사본 상태, 입수, 등록, 대출
BOOKS: tuple[tuple, ...] = (
    # 문학 10
    (
        "바람이 머무는 집",
        "813.7",
        False,
        ("available", "available"),
        A,
        REGISTERED,
        ("2026-09-03", "2026-10-02", "2026-11-02", "2026-11-09"),
    ),
    (
        "겨울 정원의 편지",
        "813.7",
        False,
        ("available",),
        A,
        REGISTERED,
        ("2026-09-10", "2026-11-03", "2026-11-12"),
    ),
    ("새벽 기차", "813.6", False, ("available",), D, REGISTERED, ("2026-10-05", "2026-11-04")),
    ("시인의 산책", "811.7", False, ("available",), A, REGISTERED, ("2026-11-06",)),
    ("작은 섬의 여름", "813.7", False, ("available",), A, REGISTERED, ()),
    ("오래된 서점", "813.7", False, ("available",), A, REGISTERED, ("2026-09-15",)),
    (
        "달빛 그림책",
        "813.8",
        True,
        ("available", "available"),
        A,
        REGISTERED,
        ("2026-09-20", "2026-10-11", "2026-11-05", "2026-11-10", "2026-11-14!"),
    ),
    ("고양이 동화집", "813.8", True, ("available",), D, REGISTERED, ("2026-10-20", "2026-11-07")),
    ("숲속 친구들", "813.8", True, ("available",), A, REGISTERED, ("2026-11-08",)),
    ("마음의 온도", "814.7", False, ("damaged",), A, REGISTERED, ("2026-09-08",)),
    # 자연과학 6
    (
        "별자리 이야기",
        "443",
        True,
        ("available", "available"),
        A,
        REGISTERED,
        ("2026-09-12", "2026-10-15", "2026-11-11"),
    ),
    (
        "공룡 대탐험",
        "457",
        True,
        ("available",),
        A,
        REGISTERED,
        ("2026-09-22", "2026-10-01", "2026-10-25", "2026-11-01?"),
    ),
    ("곤충 관찰 일기", "495", True, ("available",), D, REGISTERED, ("2026-10-30?",)),
    ("어린이 실험실", "407", True, ("lost",), A, REGISTERED, ("2026-09-05",)),
    ("우주의 기원", "443.1", False, ("available",), A, REGISTERED, ("2026-10-08",)),
    ("생물의 진화", "476", False, ("available",), A, REGISTERED, ()),
    # 기술과학 4
    (
        "집밥 요리책",
        "594.5",
        False,
        ("available", "available"),
        A,
        REGISTERED,
        ("2026-09-18", "2026-10-18", "2026-11-16!"),
    ),
    ("아기 건강 백과", "598.1", False, ("available",), A, REGISTERED, ("2026-10-28",)),
    ("코딩 첫걸음", "566", False, ("available",), A, REGISTERED, ()),
    ("텃밭 가꾸기", "523", False, ("available",), D, REGISTERED, ()),
    # 사회과학 4
    ("경제 쉽게 읽기", "320", False, ("available",), A, REGISTERED, ("2026-10-12",)),
    ("우리 동네 이야기", "331", False, ("available",), A, REGISTERED, ()),
    ("교육의 미래", "370", False, ("available",), A, REGISTERED, ("2026-09-25",)),
    ("법 없이도 사는 법", "360", False, ("lost",), A, REGISTERED, ()),
    # 역사 4
    (
        "조선의 하루",
        "911.05",
        False,
        ("available",),
        A,
        REGISTERED,
        ("2026-09-02", "2026-10-03", "2026-11-17!"),
    ),
    ("세계 여행 지도", "981", False, ("available",), A, REGISTERED, ()),
    ("위인 열 명", "990", True, ("available",), A, REGISTERED, ("2026-10-22",)),
    ("옛 지도 여행", "981.1", False, ("withdrawn",), A, REGISTERED, ("2026-09-07", "2026-09-27")),
    # 예술 3
    ("수채화 시작하기", "651", False, ("available",), A, REGISTERED, ()),
    ("동요 모음", "670", True, ("available",), D, REGISTERED, ("2026-10-30",)),
    ("축구의 모든 것", "695", False, ("available",), A, REGISTERED, ("2026-11-18!",)),
    # 철학·종교 2
    ("생각하는 법", "160", False, ("available",), A, REGISTERED, ()),
    ("마음 공부", "220", False, ("available",), U, REGISTERED, ()),
    # 청구기호로만 분류 1
    ("동네 산책 지도", "청:981.2-김12ㄷ", False, ("available",), A, REGISTERED, ()),
    # 분류 없음 4 (별치기호 청구기호 포함)
    ("이름 없는 노트", None, False, ("available",), D, REGISTERED, ()),
    ("그림 낱말 카드", "청:아 710-가12", True, ("available",), A, REGISTERED, ("2026-11-06",)),
    ("마을 신문 모음", None, False, ("available", "withdrawn"), A, REGISTERED, ()),
    ("오래된 사진첩", None, False, ("available",), U, REGISTERED, ()),
    # 한 번도 빌리지 않은 책 8(안 빌린 책 목록이 20을 넘게)
    ("백과사전 첫 권", "030", False, ("available",), A, REGISTERED, ()),
    ("신문 읽기", "070", False, ("available",), A, REGISTERED, ()),
    ("한글 맞춤법", "711", False, ("available",), A, REGISTERED, ()),
    ("영어 첫걸음", "740", False, ("available",), A, REGISTERED, ()),
    ("고전 시가", "811", False, ("available",), A, REGISTERED, ()),
    ("단편 소설선", "813.6", False, ("available",), A, REGISTERED, ()),
    ("여행 수필", "816", False, ("available",), A, REGISTERED, ()),
    ("요가 입문", "517", False, ("available",), A, REGISTERED, ()),
    # 최근 등록 2(안 빌린 책의 기간 중 등록)
    ("새로 온 그림책", "813.8", True, ("available",), A, NEW, ()),
    ("새로 온 과학책", "400", False, ("available",), A, NEW, ()),
)

EXTERNAL_BOOKS: tuple[tuple, ...] = (
    ("외부 기관 소설", "813.7", ("available", "on_loan")),
    ("외부 기관 과학책", "443", ("available",)),
    ("외부 기관 요리책", "594", ("lost",)),
)


# 큐레이션 평가 기관(자체 대출·외부 대출 둘에 같은 책). 분석 라벨의 숫자가 바뀌지 않도록 분석 기관과
# 따로 둔다. 주제 `공룡`·`우주`는 서명 키워드로 추천 가능한 책이 3권 이상 찾힌다. 서명, KDC, 소개,
# 사본 상태.
CURATION_BOOKS: tuple[tuple, ...] = (
    (
        "공룡 대탐험",
        "457",
        "공룡의 종류와 사는 곳을 그림으로 보여 주는 어린이 과학책",
        ("available",),
    ),
    ("공룡 화석의 비밀", "457", "화석으로 공룡의 몸과 생활을 알아보는 책", ("available",)),
    ("꼬마 공룡 뚜비", "813.8", "아기 공룡이 친구를 찾아 떠나는 그림책", ("on_loan",)),
    ("공룡 시대 이야기", "457", "중생대 공룡이 살던 시대를 소개하는 책", ("available",)),
    ("공룡 도감 옛판", "457", "예전 판 공룡 도감", ("withdrawn",)),
    ("우주 여행 안내서", "443", "태양계 행성을 차례로 여행하듯 소개하는 책", ("available",)),
    ("별과 우주의 탄생", "443", "별이 태어나고 우주가 넓어지는 과정을 쉽게 설명", ("available",)),
    ("우주 정거장의 하루", "559", "우주 비행사가 정거장에서 보내는 하루", ("available",)),
    ("집밥 한 그릇", "594.5", "매일 먹는 집밥 요리법", ("available",)),
    ("바다로 간 고래", "813.8", "고래 가족의 바다 여행 그림책", ("available",)),
)
PENDING_CURATION = "가을 그림책 모음"  # 큐레이션 자체 대출 기관에 미리 있는 승인 대기 큐레이션

# ISBN 앞자리: 분석 기관 책 100, 외부 대출 기관 책 200, 큐레이션 책 300, 희망도서(소장 안 함) 900
BOOK_ISBN, EXTERNAL_ISBN, CURATION_ISBN, WISH_ISBN = 100, 200, 300, 900

# 희망도서: (서명, ISBN 번호(None이면 ISBN 없음), 신청 회원 번호들). 같은 ISBN을 두 회원이 신청한
# 책 하나, ISBN 없는 신청 하나. 분석 기관(자체 대출)의 회원 `평가회원1~5`가 신청한다.
WISHES: tuple[tuple, ...] = (
    ("숲속 동물 사전", 1, (1, 2)),
    ("별자리 이야기", 2, (3,)),
    ("우리 동네 지도", 3, (4,)),
    ("제목만 아는 책", None, (5,)),
)
# 큐레이션 외부 대출 기관의 희망도서(신청 회원 `평가회원9`)
EXTERNAL_WISHES: tuple[tuple, ...] = (("바다 생물 도감", 4), ("곤충 관찰 일기", 5))
PENDING_PURCHASE = (
    "11월 보충 구매"  # 분석 기관에 미리 있는 승인 대기 구매 요청서(별자리 이야기 1권)
)


def eval_isbn(group: int, n: int) -> str:
    """평가용 가상 ISBN-13(체크 숫자가 맞다). `group`은 위의 앞자리, `n`은 0~9999."""
    first12 = f"97911{group:03d}{n:04d}"
    return first12 + isbn13_check_digit(first12)


@dataclass(frozen=True)
class EvalLibraries:
    internal_id: int
    external_id: int
    titles: dict[str, int]  # 자체 대출 기관의 서명 → 기관 도서 id
    curation_internal_id: int = 0
    curation_external_id: int = 0
    curation_titles: dict[str, int] | None = None  # 큐레이션 자체 대출 기관의 서명 → id


@contextmanager
def fixed_clock() -> Iterator[None]:
    """오늘을 고정하고, 지금은 NOW부터 실제로 흐른 만큼 더한다(실행 시간 기록이 남게)."""
    original_today, original_now = clock.today, clock.now
    started = original_now()
    clock.today = lambda: TODAY  # type: ignore[assignment]
    clock.now = lambda: NOW + (original_now() - started)  # type: ignore[assignment]
    try:
        yield
    finally:
        clock.today, clock.now = original_today, original_now  # type: ignore[assignment]


async def _insert(session: AsyncSession, table: str, returning: bool = True, **values) -> int:
    cols = ", ".join(values)
    params = ", ".join(f":{k}" for k in values)
    tail = " RETURNING id" if returning else ""
    row = await session.execute(
        text(f"INSERT INTO {table} ({cols}) VALUES ({params}){tail}"), values
    )
    return row.scalar_one() if returning else 0


async def _library(session: AsyncSession, name: str, loan_mode: str) -> int:
    return await _insert(
        session,
        "libraries",
        name=name,
        type="small_library",
        loan_mode=loan_mode,
        default_loan_days=14,
    )


def _classification(value: str | None) -> tuple[str | None, str | None]:
    """(KDC, 청구기호)."""
    if value is None:
        return None, None
    if value.startswith("청:"):
        return None, value.removeprefix("청:")
    return value, f"{value}-평가"


async def _book(
    session: AsyncSession, library_id: int, title: str, kdc, created_at, isbn: str
) -> int:
    author = "평가 저자"
    return await _insert(
        session,
        "library_books",
        library_id=library_id,
        isbn=isbn,
        title=title,
        author=author,
        author_keys=author_keys(author),
        kdc=kdc,
        created_at=created_at,
    )


async def _wish(session: AsyncSession, library_id: int, member_id: int, title: str, isbn) -> None:
    await _insert(
        session,
        "book_requests",
        returning=False,
        library_id=library_id,
        member_id=member_id,
        title=title,
        title_key=match_key(title),
        isbn=isbn,
    )


async def build_libraries(session: AsyncSession, suffix: str = "") -> EvalLibraries:
    """기관 이름은 유일해야 해서, 같은 트랜잭션에서 두 번 만들 때는 suffix를 준다."""
    internal = await _library(session, f"평가용 자체 대출 작은도서관{suffix}", "internal")
    external = await _library(session, f"평가용 외부 대출 작은도서관{suffix}", "external")
    members = [
        await _insert(
            session, "members", library_id=internal, member_number=f"E{i:04d}", name=f"평가회원{i}"
        )
        for i in range(1, 6)
    ]
    titles: dict[str, int] = {}
    accession = 0
    for index, (title, cls, children, statuses, acquisition, created, loans) in enumerate(BOOKS):
        kdc, call_number = _classification(cls)
        book_id = await _book(session, internal, title, kdc, created, eval_isbn(BOOK_ISBN, index))
        titles[title] = book_id
        if children:
            await _insert(
                session,
                "library_book_audiences",
                returning=False,
                library_id=internal,
                library_book_id=book_id,
                audience="children",
                audience_source="manual",
            )
        holdings = []
        for status in statuses:
            accession += 1
            holdings.append(
                await _insert(
                    session,
                    "holdings",
                    library_id=internal,
                    library_book_id=book_id,
                    accession_number=f"EV{accession:05d}",
                    call_number=call_number,
                    status=status,
                    acquisition_type=acquisition,
                    purchase_price=13000 if acquisition == A else None,
                    donor="평가 기증자" if acquisition == D else None,
                )
            )
        for n, raw in enumerate(loans):
            active, overdue = raw.endswith("!"), raw.endswith("?")
            loaned = date.fromisoformat(raw.rstrip("!?"))
            due = loaned + timedelta(days=14)
            holding = holdings[n % len(holdings)]  # 같은 사본의 대출이 겹치지 않게 돌아가며
            await _insert(
                session,
                "loans",
                library_id=internal,
                holding_id=holding,
                member_id=members[(index + n) % len(members)],
                loaned_on=loaned,
                due_on=due if not overdue else min(due, TODAY - timedelta(days=4)),
                returned_on=None if active or overdue else loaned + timedelta(days=7),
            )
            if active or overdue:
                await session.execute(
                    text("UPDATE holdings SET status = 'on_loan' WHERE id = :id"), {"id": holding}
                )
    for n, (title, kdc, statuses) in enumerate(EXTERNAL_BOOKS):
        book_id = await _book(
            session, external, title, kdc, REGISTERED, eval_isbn(EXTERNAL_ISBN, n)
        )
        for status in statuses:
            accession += 1
            await _insert(
                session,
                "holdings",
                library_id=external,
                library_book_id=book_id,
                accession_number=f"EX{accession:05d}",
                call_number=f"{kdc}-외부",
                status=status,
                acquisition_type=A,
                purchase_price=13000,
                source="imported",
                last_synced_at=datetime(2026, 11, 18, 0, 0, tzinfo=UTC),
            )
    for title, number, requesters in WISHES:
        isbn = eval_isbn(WISH_ISBN, number) if number is not None else None
        for who in requesters:
            await _wish(session, internal, members[who - 1], title, isbn)
    purchase = await _insert(
        session,
        "purchase_requests",
        library_id=internal,
        title=PENDING_PURCHASE,
        status="pending_approval",
    )
    await _insert(
        session,
        "purchase_request_items",
        returning=False,
        library_id=internal,
        purchase_request_id=purchase,
        position=1,
        isbn=eval_isbn(WISH_ISBN, 2),
        title="별자리 이야기",
        quantity=1,
        reason_kind="book_request",
    )
    curation_internal, curation_titles = await _curation_library(
        session, f"평가용 큐레이션 자체 대출 작은도서관{suffix}", "internal", "CI"
    )
    curation_external, _ = await _curation_library(
        session, f"평가용 큐레이션 외부 대출 작은도서관{suffix}", "external", "CE"
    )
    external_member = await _insert(
        session, "members", library_id=curation_external, member_number="E0009", name="평가회원9"
    )
    for title, number in EXTERNAL_WISHES:
        await _wish(
            session, curation_external, external_member, title, eval_isbn(WISH_ISBN, number)
        )
    pending = await _insert(
        session,
        "curations",
        library_id=curation_internal,
        title=PENDING_CURATION,
        status="pending_approval",
    )
    for position, title in enumerate(("꼬마 공룡 뚜비", "바다로 간 고래", "공룡 대탐험"), 1):
        await _insert(
            session,
            "curation_items",
            returning=False,
            library_id=curation_internal,
            curation_id=pending,
            position=position,
            library_book_id=curation_titles[title],
            reason="그림이 많은 책",
        )
    await session.commit()
    return EvalLibraries(
        internal,
        external,
        titles,
        curation_internal,
        curation_external,
        curation_titles,
    )


async def _curation_library(
    session: AsyncSession, name: str, loan_mode: str, prefix: str
) -> tuple[int, dict[str, int]]:
    library = await _library(session, name, loan_mode)
    titles: dict[str, int] = {}
    for n, (title, kdc, description, statuses) in enumerate(CURATION_BOOKS):
        author = "평가 저자"
        book_id = await _insert(
            session,
            "library_books",
            library_id=library,
            isbn=eval_isbn(CURATION_ISBN, n),
            title=title,
            author=author,
            author_keys=author_keys(author),
            kdc=kdc,
            description=description,
            created_at=REGISTERED,
        )
        titles[title] = book_id
        for m, status in enumerate(statuses):
            await _insert(
                session,
                "holdings",
                library_id=library,
                library_book_id=book_id,
                accession_number=f"{prefix}{n:03d}{m}",
                call_number=f"{kdc}-평가",
                status=status,
                acquisition_type=A,
                purchase_price=13000,
                source="imported" if loan_mode == "external" else "manual",
                last_synced_at=(
                    datetime(2026, 11, 18, 0, 0, tzinfo=UTC) if loan_mode == "external" else None
                ),
            )
    return library, titles
