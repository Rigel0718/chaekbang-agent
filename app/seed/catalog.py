"""도서 50권(기관 공통)과 기관별 소장 사본 시드. 같은 seed면 같은 데이터가 만들어진다.

- 어린이 도서 15권, 일반 도서 30권(ISBN·정가 있음), ISBN·정가 없는 기증 도서 5권
- 사본: 기관마다 도서 약 35권, 일부는 2~3권. 분실·훼손 사본을 섞는다.
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


async def _book_ids(session: AsyncSession, books: list[dict]) -> list[int]:
    """books 순서대로 id. ISBN이 있으면 ISBN으로, 없으면 제목+저자로 찾는다."""
    by_isbn = dict(
        (
            await session.execute(
                select(Book.isbn, Book.id).where(
                    Book.isbn.in_([b["isbn"] for b in books if b["isbn"]])
                )
            )
        ).all()
    )
    pairs = [(b["title"], b["author"]) for b in books if b["isbn"] is None]
    by_title = {
        (t, a): i
        for t, a, i in (
            await session.execute(
                select(Book.title, Book.author, Book.id).where(
                    Book.isbn.is_(None), tuple_(Book.title, Book.author).in_(pairs)
                )
            )
        ).all()
    }
    return [by_isbn[b["isbn"]] if b["isbn"] else by_title[(b["title"], b["author"])] for b in books]


async def seed_catalog(
    session: AsyncSession, seed: int, library_ids: dict[str, int]
) -> dict[str, tuple[int, int]]:
    books = generate_books(seed)

    with_isbn = [b for b in books if b["isbn"]]
    result = await session.execute(
        insert(Book)
        .values(with_isbn)
        .on_conflict_do_nothing(index_elements=["isbn"])
        .returning(Book.id)
    )
    created_books = len(result.all())
    # ISBN 없는 도서는 UNIQUE 키가 없어 제목+저자로 있는지 먼저 본다.
    existing = set(
        (
            await session.execute(
                select(Book.title, Book.author).where(
                    Book.isbn.is_(None),
                    tuple_(Book.title, Book.author).in_(
                        [(b["title"], b["author"]) for b in books if not b["isbn"]]
                    ),
                )
            )
        ).all()
    )
    missing = [b for b in books if not b["isbn"] and (b["title"], b["author"]) not in existing]
    if missing:
        await session.execute(insert(Book).values(missing))
        created_books += len(missing)

    ids = await _book_ids(session, books)
    holding_rows = []
    for offset, lib in enumerate(LIBRARIES, start=1):
        for row in generate_holdings(seed, books, lib.key, offset):
            book_index = row.pop("book_index")
            holding_rows.append(
                {**row, "library_id": library_ids[lib.key], "book_id": ids[book_index]}
            )
    result = await session.execute(
        insert(Holding)
        .values(holding_rows)
        .on_conflict_do_nothing(index_elements=["library_id", "accession_number"])
        .returning(Holding.id)
    )
    created_holdings = len(result.all())
    return {
        "books": (created_books, len(books) - created_books),
        "holdings": (created_holdings, len(holding_rows) - created_holdings),
    }
