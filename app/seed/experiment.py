"""실험 장서: 받은 파일을 개발 DB의 공식 서지와 가상 기관으로 넣는다.

파일은 둘이다. YES24 원본(`evals/collection/fetch.py`가 한 번 받아 둔 525권)과 같은 ISBN의
정보나루·카카오 값(`evals/collection/sources.py`). 새 출처 파일이 있으면 세 출처를 채움과 같은 규칙
(`app/central/sources.merge`)으로 합치고, 없으면 YES24 값만으로 만든다. 비교 실험을 위해 쓸 출처를
고를 수 있다(`use`).

추천 실험(`add-recommendation-experiments`)의 바탕이다. 운영자가 `scripts/seed_experiment.py`로
개발 환경에서만 돌린다. 시드(`scripts/seed.py`)와 따로라 파일이 없어도 시드는 돈다.

- 공식 서지는 서지정보 채움과 같은 함수(`create_official`)로 만든다. 기여자와 시리즈 키가 함께
  생기고, 이미 있는 공식 서지는 고치지 않는다.
- 가상 기관 하나가 기관 도서와 사본으로 소장한다. 어떤 책이 어떤 상태인지는 ISBN 순서 번호로 정해
  난수를 쓰지 않는다(design 결정 16). 약 10%는 ISBN 없이 기관 값만으로 넣어 기관 도서 벡터와 저자
  키 경로가 실제 값으로 쓰이게 한다.
- 어린이 구분은 등록·가져오기와 같은 경로다: 연결된 책은 외부 분류(`apply_category`), ISBN 없는
  책은 서가 위치(`apply_file_row`).
- 청구기호는 비워 둔다. KDC는 공식 서지(정보나루)에만 있고 기관 값으로 지어내지 않는다. 회원, 대출,
  도서관 안내는 만들지 않는다.
- 고른 출처 모두 서명·저자가 없는 책은 넣지 않는다. 순서 번호는 비워 둔 채 다음 책으로 가서 다른
  책의 등록번호(책 키)가 밀리지 않는다.
- 다시 돌려도 같은 결과다. 있는 행은 찾아서 건너뛰고 고치지 않는다. 가상 기관 밖은 건드리지 않는다.
- 지우기(`purge_experiment`)는 가상 기관과 그 기관만 참조하던 공식 서지를 지운다. 출처를 바꿔 다시
  넣을 때 쓴다(이미 있는 공식 서지는 고치지 않는 규칙 때문).
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.external.data4library.parsing import parse_book
from app.central.external.kakao.parsing import parse_document
from app.central.external.yes24.parsing import Yes24Item, parse_item
from app.central.models import Book
from app.central.official_books import create_official
from app.central.sources import OfficialValues, from_yes24, merge
from app.core.isbn import InvalidIsbnError, normalize_isbn
from app.core.model_base import Base
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


SOURCE_NAMES = ("data4library", "kakao", "yes24")


@dataclass(frozen=True)
class Collection:
    fetched_on: str
    shelves: dict[str, str]  # 분야 key → 서가 위치
    books: list[dict[str, Any]]  # YES24 원본: {"field", "rank", "item"}
    # ISBN → 새 출처 파일의 행({"data4library": {...}, "kakao": {...}}). None이면 YES24 값만 쓴다
    sources: dict[str, dict[str, Any]] | None = None
    use: frozenset[str] = frozenset(SOURCE_NAMES)  # 합칠 출처


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


def load_sources(path: Path) -> dict[str, dict[str, Any]] | None:
    """새 출처 파일의 ISBN별 행. 파일이 없으면 None이다(YES24 값만으로 넣는다)."""
    if not path.exists():
        return None
    document = json.loads(path.read_text(encoding="utf-8"))
    return {row["isbn"]: row for row in document["books"]}


def _payload(row: dict[str, Any], source: str, key: str) -> list[dict[str, Any]]:
    entry = row.get(source)
    return list(entry.get(key) or []) if isinstance(entry, dict) else []


def official_values(collection: Collection, item: Yes24Item) -> OfficialValues | None:
    """그 책의 공식 서지 값. 고른 출처 모두 서명·저자가 없으면 None이다."""
    if collection.sources is None:
        return from_yes24(item)
    isbn = _isbn(item)
    row = collection.sources.get(isbn, {})
    use = collection.use
    d4l = (
        [parse_book(b) for b in _payload(row, "data4library", "books")]
        if "data4library" in use
        else []
    )
    kakao = (
        [parse_document(d) for d in _payload(row, "kakao", "documents")] if "kakao" in use else []
    )
    yes24 = [item] if "yes24" in use else []
    merged = merge(isbn, d4l, kakao, yes24)
    return merged if isinstance(merged, OfficialValues) else None


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
    session: AsyncSession, library_id: int, values: OfficialValues, isbn: str | None
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
            LibraryBook.title == values.title,
            LibraryBook.author == values.author,
        )
    found = await session.scalar(statement)
    if found is not None:
        return found, False
    book = None
    if isbn is not None:
        book = await create_official(session, isbn, values)
    library_book = LibraryBook(
        library_id=library_id,
        isbn=isbn,
        book_id=book.id if book is not None else None,
        title=values.title,
        author=values.author,
        publisher=values.publisher,
        published_date=values.published_date,
        list_price=values.list_price,
        # 기관 파일에는 소개가 드물다. ISBN 없는 책만 기관 값으로 소개를 둔다
        description=values.description if book is None else None,
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
    missing = 0
    known_isbns = set(await session.scalars(select(Book.isbn)))
    for i, (item, field) in enumerate(rows):
        plan = layout(i)
        values = official_values(collection, item)
        if values is None:
            missing += 1  # 순서 번호 i는 비워 둔다(다른 책의 등록번호가 밀리지 않게)
            continue
        isbn = _isbn(item) if plan.with_isbn else None
        shelf = collection.shelves.get(field, GENERAL_SHELF)
        if isbn is not None:
            counts["books"][1 if isbn in known_isbns else 0] += 1
            known_isbns.add(isbn)
        library_book, created = await _library_book(session, library_id, values, isbn)
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
            purchased = isbn is not None and values.list_price is not None
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
                        values.list_price * PURCHASE_RATE_PERCENT // 100 if purchased else None
                    ),
                )
            )
            counts["holdings"][0] += 1
    await session.flush()
    report |= {table: (made, skipped) for table, (made, skipped) in counts.items()}
    report["missing_books"] = (missing, 0)  # 고른 출처 모두 서명·저자가 없어 넣지 않은 책
    return report


def _library_tables() -> list:
    """기관에 속한 테이블(`library_id` 열이 있는 것). 참조하는 쪽이 먼저 오게 늘어놓는다.

    모든 모델을 등록해야 빠지는 테이블이 없다(`app/models.py`).
    """
    import app.models  # noqa: F401, PLC0415 - 모든 테이블을 metadata에 등록한다

    return [
        table
        for table in reversed(Base.metadata.sorted_tables)
        if "library_id" in table.c and table.name != "libraries"
    ]


async def purge_experiment(session: AsyncSession) -> dict[str, int]:
    """가상 기관과 그 기관만 참조하던 공식 서지를 지운다. 테이블별 지운 건수를 돌려준다.

    커밋은 부르는 쪽이 한다.

    다른 기관이 참조하는 공식 서지는 남긴다. 기여자와 공식 서지 벡터는 공식 서지와 함께 지워진다.
    """
    library_id = await session.scalar(select(Library.id).where(Library.name == LIBRARY_NAME))
    if library_id is None:
        return {}
    only_ours = list(
        await session.scalars(
            select(LibraryBook.book_id)
            .where(LibraryBook.library_id == library_id, LibraryBook.book_id.is_not(None))
            .except_(
                select(LibraryBook.book_id).where(
                    LibraryBook.library_id != library_id, LibraryBook.book_id.is_not(None)
                )
            )
        )
    )
    deleted: dict[str, int] = {}
    for table in _library_tables():
        result = await session.execute(delete(table).where(table.c.library_id == library_id))
        if result.rowcount:
            deleted[table.name] = result.rowcount
    result = await session.execute(delete(Library).where(Library.id == library_id))
    deleted["libraries"] = result.rowcount
    if only_ours:
        contributors = await session.scalar(
            text("SELECT count(*) FROM book_contributors WHERE book_id = ANY(:ids)"),
            {"ids": only_ours},
        )
        result = await session.execute(delete(Book).where(Book.id.in_(only_ours)))
        deleted["books"] = result.rowcount
        deleted["book_contributors"] = contributors
    await session.flush()
    return deleted
