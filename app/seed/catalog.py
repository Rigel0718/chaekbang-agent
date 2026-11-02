"""catalog 시드: 도서 50권과 그중 약 35권의 매장 재고. 같은 seed면 같은 데이터가 만들어진다."""

import random
from datetime import date, timedelta

from faker import Faker
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.matching.isbn import isbn13_check_digit
from app.models.catalog import Book, StoreInventory

BOOK_COUNT = 50
INVENTORY_COUNT = 35

_ADJECTIVES = [
    "따뜻한",
    "작은",
    "푸른",
    "조용한",
    "느린",
    "반짝이는",
    "오래된",
    "낯선",
    "용감한",
    "다정한",
    "깊은",
    "하얀",
    "마지막",
    "보이지 않는",
    "기묘한",
    "여름의",
    "겨울의",
    "어느 날의",
]
_NOUNS = [
    "고양이",
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
    "모자",
]
# Faker ko_KR에는 한국어 문장 생성기가 없어 소개 문구는 템플릿으로 만든다.
_BLURBS = [
    "{title}을(를) 둘러싼 잔잔한 이야기. 데모용 가짜 소개입니다.",
    "{author} 작가가 그려 낸 {title}의 하루. 데모용 가짜 소개입니다.",
    "아이와 함께 읽기 좋은 {title}. 데모용 가짜 소개입니다.",
]
_PUBLISHERS = ["새벽별출판", "가람책", "두레북스", "온누리아이", "작은씨앗", "물결출판사"]
_SHELVES = [
    "그림책 A-1",
    "그림책 A-2",
    "동화 B-1",
    "청소년 B-2",
    "소설 C-1",
    "에세이 C-2",
    "인문 D-1",
]


def generate_books(seed: int) -> list[dict]:
    fake = Faker("ko_KR")
    fake.seed_instance(seed)
    rng = random.Random(seed)

    titles = rng.sample([f"{a} {n}" for a in _ADJECTIVES for n in _NOUNS], BOOK_COUNT)
    isbns: list[str] = []
    while len(isbns) < BOOK_COUNT:
        first12 = f"97911{rng.randrange(10**7):07d}"
        isbn = first12 + isbn13_check_digit(first12)
        if isbn not in isbns:
            isbns.append(isbn)

    books = []
    for isbn, title in zip(isbns, titles, strict=True):
        author = fake.name()
        books.append(
            {
                "isbn": isbn,
                "title": title,
                "author": author,
                "publisher": rng.choice(_PUBLISHERS),
                "published_date": date(2015, 1, 1) + timedelta(days=rng.randrange(365 * 11)),
                "list_price": rng.randrange(8, 36) * 1000,
                "description": rng.choice(_BLURBS).format(title=title, author=author),
            }
        )
    return books


def generate_inventory(seed: int, books: list[dict]) -> list[dict]:
    rng = random.Random(seed + 1)
    return [
        {"isbn": b["isbn"], "quantity": rng.randrange(0, 6), "shelf_location": rng.choice(_SHELVES)}
        for b in rng.sample(books, INVENTORY_COUNT)
    ]


async def seed_catalog(session: AsyncSession, seed: int) -> dict[str, tuple[int, int]]:
    """이미 있는 ISBN은 건너뛴다. {테이블: (생성, 건너뜀)}을 돌려준다."""
    books = generate_books(seed)
    inventory = generate_inventory(seed, books)
    created_books = await _insert_missing(session, Book, books)
    created_inventory = await _insert_missing(session, StoreInventory, inventory)
    return {
        "books": (created_books, len(books) - created_books),
        "store_inventory": (created_inventory, len(inventory) - created_inventory),
    }


async def _insert_missing(session: AsyncSession, model: type, rows: list[dict]) -> int:
    stmt = insert(model).values(rows).on_conflict_do_nothing(index_elements=["isbn"])
    result = await session.execute(stmt.returning(model.isbn))
    return len(result.all())
