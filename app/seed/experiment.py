"""실험 장서: 받은 YES24 파일을 개발 DB의 공식 서지와 가상 기관으로 넣는다.

파일은 `evals/collection/fetch.py`가 한 번 받아 둔다.

추천 실험(`add-recommendation-experiments`)의 바탕이다. 운영자가 `scripts/seed_experiment.py`로
개발 환경에서만 돌린다. 시드(`scripts/seed.py`)와 따로라 파일이 없어도 시드는 돈다.

- 공식 서지는 서지정보 채움과 같은 함수(`create_official`)로 만든다. 기여자와 시리즈 키가 함께
  생기고, 이미 있는 공식 서지는 고치지 않는다.
- 가상 기관 하나가 기관 도서와 사본으로 소장한다. 어떤 책이 어떤 상태인지는 ISBN 순서 번호로 정해
  난수를 쓰지 않는다(design 결정 16). 약 10%는 ISBN 없이 기관 값만으로 넣어 기관 도서 벡터와 저자
  키 경로가 실제 값으로 쓰이게 한다.
- 어린이 구분은 등록·가져오기와 같은 경로다: 연결된 책은 외부 분류(`apply_category`), ISBN 없는
  책은 서가 위치(`apply_file_row`).
- 청구기호와 분류기호(KDC)는 비워 둔다. YES24는 KDC를 주지 않고, 분야에서 지어내면 실험이 외부
  분류를 두 번 센다. 회원, 대출, 도서관 안내는 만들지 않는다.
- 다시 돌려도 같은 결과다. 있는 행은 찾아서 건너뛰고 고치지 않는다. 가상 기관 밖은 건드리지 않는다.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.external.yes24.parsing import Yes24Item, parse_item
from app.central.models import Book
from app.central.official_books import create_official
from app.core.isbn import InvalidIsbnError, normalize_isbn
from app.core.security import hash_password
from app.features.children.service import apply_category, apply_file_row
from app.library.models.catalog import (
    AcquisitionType,
    EnrichmentStatus,
    Holding,
    HoldingStatus,
    LibraryBook,
)
from app.library.models.library import Library, LibraryType, LoanMode, StaffRole, StaffUser

LIBRARY_NAME = "실험용 가상 작은도서관"
LOGIN_PREFIX = "experiment"
LOAN_DAYS = 14
ACCESSION_PREFIX = "EX"
GENERAL_SHELF = "일반 자료실"
PURCHASE_RATE_PERCENT = 90  # 구입가 = 정가의 90%

Report = dict[str, tuple[int, int]]  # 테이블 → (생성, 건너뜀)


class CollectionMissingError(FileNotFoundError):
    pass


@dataclass(frozen=True)
class Collection:
    fetched_on: str
    shelves: dict[str, str]  # 분야 key → 서가 위치
    books: list[dict[str, Any]]  # {"field", "rank", "item"}


@dataclass(frozen=True)
class Layout:
    """ISBN 순서 번호 i로 정한 책 하나의 구성."""

    with_isbn: bool
    statuses: tuple[HoldingStatus, ...]


def layout(i: int) -> Layout:
    """design 결정 16의 표. 나머지가 표에 없으면 대출 가능 사본 1권이다."""
    if i % 10 == 3:
        return Layout(False, (HoldingStatus.AVAILABLE,))
    if i % 20 == 7:
        return Layout(True, (HoldingStatus.LOST,))
    if i % 20 == 17:
        return Layout(True, (HoldingStatus.WITHDRAWN,))
    if i % 10 == 8:
        return Layout(True, (HoldingStatus.ON_LOAN,))
    if i % 10 == 0:
        return Layout(True, (HoldingStatus.AVAILABLE, HoldingStatus.ON_LOAN))
    return Layout(True, (HoldingStatus.AVAILABLE,))


def load_collection(path: Path, shelves: dict[str, str]) -> Collection:
    """받은 파일을 읽는다. shelves는 분야 key → 서가 위치(`evals/collection/plan.py`)."""
    if not path.exists():
        raise CollectionMissingError(f"실험 장서 파일이 없습니다: {path}")
    document = json.loads(path.read_text(encoding="utf-8"))
    return Collection(document["fetched_on"], shelves, document["books"])


def _isbn(item: Yes24Item) -> str:
    try:
        return normalize_isbn(item.isbn13 or "")
    except InvalidIsbnError:
        raise ValueError(f"ISBN이 아닌 상품이 파일에 있습니다: {item.isbn13}") from None


async def _library(
    session: AsyncSession, admin_password: str, kiosk_password: str, report: Report
) -> int:
    created = await session.execute(
        insert(Library)
        .values(
            name=LIBRARY_NAME,
            type=LibraryType.SMALL_LIBRARY,
            loan_mode=LoanMode.INTERNAL,
            default_loan_days=LOAN_DAYS,
        )
        .on_conflict_do_nothing(index_elements=["name"])
        .returning(Library.id)
    )
    made = len(created.all())
    report["libraries"] = (made, 1 - made)
    library_id = await session.scalar(select(Library.id).where(Library.name == LIBRARY_NAME))
    assert library_id is not None
    rows = [
        {
            "library_id": library_id,
            "login_id": f"{LOGIN_PREFIX}-{role.value}",
            "password_hash": hash_password(password),
            "role": role,
        }
        for role, password in ((StaffRole.ADMIN, admin_password), (StaffRole.KIOSK, kiosk_password))
    ]
    # 이미 있는 계정의 비밀번호는 바꾸지 않는다
    created = await session.execute(
        insert(StaffUser)
        .values(rows)
        .on_conflict_do_nothing(index_elements=["login_id"])
        .returning(StaffUser.id)
    )
    made = len(created.all())
    report["staff_users"] = (made, len(rows) - made)
    return library_id


async def _library_book(
    session: AsyncSession, library_id: int, item: Yes24Item, isbn: str | None
) -> tuple[LibraryBook, bool]:
    """(기관 도서, 새로 만들었는지).

    ISBN이 있으면 (기관, ISBN), 없으면 (기관, 서명, 저자)로 찾는다.
    """
    statement = select(LibraryBook).where(LibraryBook.library_id == library_id)
    if isbn is not None:
        statement = statement.where(LibraryBook.isbn == isbn)
    else:
        statement = statement.where(
            LibraryBook.isbn.is_(None),
            LibraryBook.title == item.title,
            LibraryBook.author == item.author,
        )
    found = await session.scalar(statement)
    if found is not None:
        return found, False
    book = None
    if isbn is not None:
        book = await create_official(session, isbn, item)
    library_book = LibraryBook(
        library_id=library_id,
        isbn=isbn,
        book_id=book.id if book is not None else None,
        title=item.title,
        author=item.author,
        publisher=item.publisher,
        published_date=item.published_date,
        list_price=item.list_price,
        # 기관 파일에는 소개가 드물다. ISBN 없는 책만 기관 값으로 소개를 둔다
        description=item.description if book is None else None,
        enrichment_status=EnrichmentStatus.ENRICHED if book else EnrichmentStatus.PENDING,
    )
    session.add(library_book)
    await session.flush()
    await session.refresh(library_book, ["book"])
    return library_book, True


async def seed_experiment(
    session: AsyncSession, collection: Collection, admin_password: str, kiosk_password: str
) -> Report:
    """가상 기관과 실험 장서를 넣는다. 커밋은 부르는 쪽이 한다."""
    report: Report = {}
    library_id = await _library(session, admin_password, kiosk_password, report)
    rows = sorted(
        ((parse_item(row["item"]), row["field"]) for row in collection.books),
        key=lambda pair: _isbn(pair[0]),
    )
    counts = {"books": [0, 0], "library_books": [0, 0], "holdings": [0, 0]}
    known_isbns = set(await session.scalars(select(Book.isbn)))
    for i, (item, field) in enumerate(rows):
        plan = layout(i)
        isbn = _isbn(item) if plan.with_isbn else None
        shelf = collection.shelves.get(field, GENERAL_SHELF)
        if isbn is not None:
            counts["books"][1 if isbn in known_isbns else 0] += 1
            known_isbns.add(isbn)
        library_book, created = await _library_book(session, library_id, item, isbn)
        counts["library_books"][0 if created else 1] += 1
        if created:
            if isbn is not None:
                await apply_category(session, library_book)
            else:
                await apply_file_row(session, library_book, {"shelf_location": shelf})
        for copy, status in enumerate(plan.statuses):
            accession = f"{ACCESSION_PREFIX}{i + 1:05d}" + (f"-{copy + 1}" if copy else "")
            stored = await session.scalar(
                select(Holding.id).where(
                    Holding.library_id == library_id, Holding.accession_number == accession
                )
            )
            if stored is not None:
                counts["holdings"][1] += 1
                continue
            purchased = isbn is not None and item.list_price is not None
            session.add(
                Holding(
                    library_id=library_id,
                    library_book_id=library_book.id,
                    accession_number=accession,
                    shelf_location=shelf,
                    status=status,
                    acquisition_type=(
                        AcquisitionType.PURCHASED if purchased else AcquisitionType.DONATED
                    ),
                    purchase_price=(
                        item.list_price * PURCHASE_RATE_PERCENT // 100 if purchased else None
                    ),
                )
            )
            counts["holdings"][0] += 1
    await session.flush()
    report |= {table: (made, skipped) for table, (made, skipped) in counts.items()}
    return report
