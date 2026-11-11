"""서명·저자 찾기 속도. 작은도서관 규모(5,000권)에서 인덱스 없이 충분히 빠른지 본다.

오타 질의는 모든 책에 편집 거리를 계산하므로 가장 느린 경우다. 기준(각 200ms)은
`openspec/changes/add-catalog-search/design.md`의 8절에 있다. 넘으면 인덱스를 검토한다.
"""

import time

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.library.recommendation.lookup import find_books, found_in_text, suggest_books
from tests.conftest import Tenant

BOOKS = 5000
LIMIT_MS = 200

# 한글 음절을 섞어 3~6음절 서명과 2~3음절 저자를 만든다.
FILL = text(
    """
    WITH n AS (SELECT g FROM generate_series(1, :books) AS g),
    lb AS (
        INSERT INTO library_books (library_id, title, author, list_price)
        SELECT :library_id,
               (SELECT string_agg(chr(44032 + ((g * 7919 + k * 104729) % 11172)), '')
                  FROM generate_series(1, 3 + g % 4) AS k)
               || ' ' || (SELECT string_agg(chr(44032 + ((g * 31 + k * 977) % 11172)), '')
                            FROM generate_series(1, 2) AS k),
               (SELECT string_agg(chr(44032 + ((g * 131 + k * 6007) % 11172)), '')
                  FROM generate_series(1, 2 + g % 2) AS k),
               10000
          FROM n
        RETURNING id
    )
    INSERT INTO holdings (library_id, library_book_id, accession_number, acquisition_type,
                          purchase_price, status)
    SELECT :library_id, id, 'SP' || id, 'purchased', 10000, 'available' FROM lb
    """
)


async def _elapsed_ms(make, tries: int = 3) -> float:
    """세 번 재서 가장 빠른 값. 다른 테스트가 함께 돌 때의 흔들림을 덜어 낸다."""
    best = float("inf")
    for _ in range(tries):
        start = time.perf_counter()
        await make()
        best = min(best, (time.perf_counter() - start) * 1000)
    return best


async def test_lookup_speed(session: AsyncSession, library_a: Tenant) -> None:
    await session.execute(FILL, {"books": BOOKS, "library_id": library_a.id})
    await session.execute(
        text(
            "INSERT INTO library_books (library_id, title, author, list_price) "
            "VALUES (:id, '데미안', '헤르만 헤세', 10000)"
        ),
        {"id": library_a.id},
    )
    await find_books(session, library_a.id, "데미안")  # 첫 호출의 계획 준비를 빼고 잰다
    timings = {
        "find_typo": await _elapsed_ms(lambda: find_books(session, library_a.id, "데미얀 헤새")),
        "find_exact": await _elapsed_ms(lambda: find_books(session, library_a.id, "데미안")),
        "suggest": await _elapsed_ms(lambda: suggest_books(session, library_a.id, "데미ㅇ")),
        "found_in_text": await _elapsed_ms(
            lambda: found_in_text(session, library_a.id, "혹시 도서관에 데미얀 같은 책이 있을까요")
        ),
    }
    print(timings)
    slow = {name: ms for name, ms in timings.items() if ms > LIMIT_MS}
    assert not slow, f"{LIMIT_MS}ms 초과: {slow}"
