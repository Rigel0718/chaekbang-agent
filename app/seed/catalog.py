"""공식 서지와 기관별 기관 도서·소장 사본 시드. 같은 seed면 같은 데이터가 만들어진다.

- 도서 50권: 어린이 15권, 일반 30권(ISBN·정가 있음), ISBN·정가 없는 기증 도서 5권
- 공식 서지: ISBN 있는 45권. 가짜 ISBN이라 실제 공식 서지가 아니라 연결을 보여 주는 데모 값이다.
- 기관 도서: 기관마다 도서 약 35권. ISBN이 있으면 공식 서지에 연결한다.
- 사본: 기관 도서마다 1~3권. 분실·훼손 사본을 섞는다.
- 약 70%는 매입·납품(구입가 = 정가의 90%), 나머지는 기증. ISBN 없는 도서는 모두 기증이다.
"""

import random
from datetime import date, timedelta

from faker import Faker
from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.isbn import isbn13_check_digit
from app.models.catalog import (
    AcquisitionType,
    Audience,
    AudienceSource,
    Book,
    Holding,
    HoldingStatus,
    LibraryBook,
)
from app.seed.library import LIBRARIES

CHILDREN_COUNT = 15
GENERAL_COUNT = 30
NO_ISBN_COUNT = 5
BOOK_COUNT = CHILDREN_COUNT + GENERAL_COUNT + NO_ISBN_COUNT
HELD_PER_LIBRARY = 35

_ADJECTIVES = [
    "따뜻한",
    "작은",
    "푸른",
    "조용한",
    "느린",
    "반짝이는",
    "오래된",
    "낯선",
    "다정한",
    "깊은",
    "하얀",
    "마지막",
    "기묘한",
    "여름의",
    "겨울의",
    "어느 날의",
]
_NOUNS = [
    "책방",
    "숲",
    "편지",
    "바다",
    "정원",
    "기차",
    "여행",
    "도서관",
    "별",
    "우산",
    "골목",
    "섬",
    "약속",
    "식탁",
    "창문",
    "등대",
]
_KID_ADJECTIVES = ["용감한", "졸린", "배고픈", "씩씩한", "수줍은", "엉뚱한"]
_KID_NOUNS = ["공룡", "아기곰", "토끼", "펭귄", "고양이", "코끼리"]
_KID_TAILS = ["의 하루", "와 친구들", "의 모험"]
_LOCAL_TITLES = [
    "우리 마을 옛이야기",
    "동네 어르신 구술 기록",
    "주민 사진첩 2019",
    "마을 축제 이야기",
    "작은도서관 10년",
]
_PUBLISHERS = ["새벽별출판", "가람책", "두레북스", "온누리아이", "작은씨앗", "물결출판사"]
_GENERAL_KDC = ["813.7", "814.6", "818", "843", "911", "325.2", "181.7"]
_CHILDREN_KDC = ["813.8", "808.9", "470", "490"]
_GENERAL_SHELVES = ["일반 자료실 1", "일반 자료실 2", "일반 자료실 3"]
_CHILDREN_SHELVES = ["어린이 자료실 1", "어린이 자료실 2"]
_DONORS = ["주민 기증", "주민 기증", "OO초등학교 학부모회", "마을 독서 모임", None]
_BLURBS = [
    "{title}을(를) 둘러싼 잔잔한 이야기. 데모용 가짜 소개입니다.",
    "{author} 작가가 그려 낸 {title}의 하루. 데모용 가짜 소개입니다.",
]


def generate_books(seed: int) -> list[dict]:
    fake = Faker("ko_KR")
    fake.seed_instance(seed)
    rng = random.Random(seed)

    kid_titles = rng.sample(
        [f"{a} {n}{t}" for a in _KID_ADJECTIVES for n in _KID_NOUNS for t in _KID_TAILS],
        CHILDREN_COUNT,
    )
    general_titles = rng.sample([f"{a} {n}" for a in _ADJECTIVES for n in _NOUNS], GENERAL_COUNT)
    isbns: list[str] = []
    while len(isbns) < CHILDREN_COUNT + GENERAL_COUNT:
        first12 = f"97911{rng.randrange(10**7):07d}"
        isbn = first12 + isbn13_check_digit(first12)
        if isbn not in isbns:
            isbns.append(isbn)

    books = []
    for i, title in enumerate(kid_titles + general_titles):
        children = i < CHILDREN_COUNT
        author = fake.name()
        books.append(
            {
                "isbn": isbns[i],
                "title": title,
                "author": author,
                "publisher": rng.choice(_PUBLISHERS),
                "published_date": date(2015, 1, 1) + timedelta(days=rng.randrange(365 * 11)),
                "list_price": rng.randrange(8, 36) * 1000,
                "kdc": rng.choice(_CHILDREN_KDC if children else _GENERAL_KDC),
                "audience": Audience.CHILDREN if children else Audience.GENERAL,
                "audience_source": AudienceSource.MANUAL if children else AudienceSource.DEFAULT,
                "description": rng.choice(_BLURBS).format(title=title, author=author),
            }
        )
    for title in _LOCAL_TITLES[:NO_ISBN_COUNT]:
        books.append(
            {
                "isbn": None,
                "title": title,
                "author": fake.name(),
                "publisher": None,
                "published_date": None,
                "list_price": None,
                "kdc": "911",
                "audience": Audience.GENERAL,
                "audience_source": AudienceSource.DEFAULT,
                "description": None,
            }
        )
    return books


def _call_number(book: dict, copy: int) -> str:
    """분류기호-저자 첫 글자+제목 첫 글자 (복본은 c.2, c.3). 데모용 단순 규칙이다."""
    base = f"{book['kdc']}-{book['author'][0]}{book['title'][0]}"
    return base if copy == 1 else f"{base} c.{copy}"


def generate_holdings(seed: int, books: list[dict], library_key: str, offset: int) -> list[dict]:
    """한 기관의 사본. book_index는 books 안의 위치다."""
    rng = random.Random(seed + offset)
    chosen = sorted(rng.sample(range(len(books)), HELD_PER_LIBRARY))
    rows = []
    for index in chosen:
        book = books[index]
        copies = rng.choices([1, 2, 3], weights=[7, 2, 1])[0]
        for copy in range(1, copies + 1):
            purchased = book["isbn"] is not None and rng.random() < 0.7
            rows.append(
                {
                    "book_index": index,
                    "accession_number": f"{library_key[:3].upper()}{len(rows) + 1:05d}",
                    "call_number": _call_number(book, copy),
                    "shelf_location": rng.choice(
                        _CHILDREN_SHELVES
                        if book["audience"] == Audience.CHILDREN
                        else _GENERAL_SHELVES
                    ),
                    "status": rng.choices(
                        [HoldingStatus.AVAILABLE, HoldingStatus.LOST, HoldingStatus.DAMAGED],
                        weights=[18, 1, 1],
                    )[0],
                    "acquisition_type": AcquisitionType.PURCHASED
                    if purchased
                    else AcquisitionType.DONATED,
                    "purchase_price": book["list_price"] * 9 // 10 if purchased else None,
                    "donor": None if purchased else rng.choice(_DONORS),
                }
            )
    # 분실·훼손이 하나도 안 나오면 첫 두 권을 바꿔 둔다 (시드 데이터에 항상 있게).
    if not any(r["status"] == HoldingStatus.LOST for r in rows):
        rows[0]["status"] = HoldingStatus.LOST
    if not any(r["status"] == HoldingStatus.DAMAGED for r in rows):
        rows[1]["status"] = HoldingStatus.DAMAGED
    return rows


async def _seed_official(session: AsyncSession, books: list[dict]) -> tuple[dict[str, int], int]:
    """(ISBN별 공식 서지 id, 새로 만든 건수). 어린이 구분은 기관 도서에 두므로 넣지 않는다."""
    rows = [
        {k: v for k, v in b.items() if k not in ("audience", "audience_source")}
        for b in books
        if b["isbn"]
    ]
    result = await session.execute(
        insert(Book).values(rows).on_conflict_do_nothing(index_elements=["isbn"]).returning(Book.id)
    )
    created = len(result.all())
    ids = await session.execute(
        select(Book.isbn, Book.id).where(Book.isbn.in_([r["isbn"] for r in rows]))
    )
    return dict(ids.all()), created


async def _seed_library_books(session: AsyncSession, rows: list[dict]) -> int:
    """기관 도서를 만들고 새로 만든 건수를 돌려준다."""
    with_isbn = [r for r in rows if r["isbn"]]
    result = await session.execute(
        insert(LibraryBook)
        .values(with_isbn)
        .on_conflict_do_nothing(index_elements=["library_id", "isbn"])
        .returning(LibraryBook.id)
    )
    created = len(result.all())
    # ISBN 없는 도서는 UNIQUE 키가 없어 기관·제목·저자로 있는지 먼저 본다.
    without_isbn = [r for r in rows if not r["isbn"]]
    keys = [(r["library_id"], r["title"], r["author"]) for r in without_isbn]
    existing = set(
        (
            await session.execute(
                select(LibraryBook.library_id, LibraryBook.title, LibraryBook.author).where(
                    LibraryBook.isbn.is_(None),
                    tuple_(LibraryBook.library_id, LibraryBook.title, LibraryBook.author).in_(keys),
                )
            )
        ).all()
    )
    missing = [r for r, key in zip(without_isbn, keys, strict=True) if key not in existing]
    if missing:
        await session.execute(insert(LibraryBook).values(missing))
    return created + len(missing)


async def _library_book_ids(session: AsyncSession, library_id: int) -> dict[tuple, int]:
    """기관의 도서 id. ISBN이 있으면 ISBN으로, 없으면 제목+저자로 찾는다."""
    rows = await session.execute(
        select(LibraryBook.isbn, LibraryBook.title, LibraryBook.author, LibraryBook.id).where(
            LibraryBook.library_id == library_id
        )
    )
    return {_key(isbn, title, author): id for isbn, title, author, id in rows.all()}


def _key(isbn: str | None, title: str, author: str) -> tuple:
    return (isbn,) if isbn else (title, author)


async def seed_catalog(
    session: AsyncSession, seed: int, library_ids: dict[str, int]
) -> dict[str, tuple[int, int]]:
    books = generate_books(seed)
    official_ids, created_books = await _seed_official(session, books)

    holdings_by_library = {
        lib.key: generate_holdings(seed, books, lib.key, offset)
        for offset, lib in enumerate(LIBRARIES, start=1)
    }
    library_book_rows = [
        {
            **books[index],
            "library_id": library_ids[key],
            "book_id": official_ids.get(books[index]["isbn"]),
        }
        for key, rows in holdings_by_library.items()
        for index in sorted({row["book_index"] for row in rows})
    ]
    created_library_books = await _seed_library_books(session, library_book_rows)

    holding_rows = []
    for key, rows in holdings_by_library.items():
        library_id = library_ids[key]
        ids = await _library_book_ids(session, library_id)
        for row in rows:
            book = books[row.pop("book_index")]
            holding_rows.append(
                {
                    **row,
                    "library_id": library_id,
                    "library_book_id": ids[_key(book["isbn"], book["title"], book["author"])],
                }
            )
    result = await session.execute(
        insert(Holding)
        .values(holding_rows)
        .on_conflict_do_nothing(index_elements=["library_id", "accession_number"])
        .returning(Holding.id)
    )
    created_holdings = len(result.all())
    return {
        "books": (created_books, len(official_ids) - created_books),
        "library_books": (created_library_books, len(library_book_rows) - created_library_books),
        "holdings": (created_holdings, len(holding_rows) - created_holdings),
    }
