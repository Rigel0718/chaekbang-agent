"""비슷한 책의 기준 책 20권과 최근 기록 10개를 규칙으로 고른다.

    uv run python -m evals.recommendation.pick [--force]

난수를 쓰지 않는다. 책 키의 SHA-256 순서로 뽑아 늘 같은 책이 나온다. 남겨 둔 분야의 책과 추천할 수
없는 책은 뽑지 않는다. 결과는 `data/seeds.json`(저장소 밖)에 쓰고, 사용자가 고칠 수 있다. 고친
파일이 기준이라 파일이 있으면 덮어쓰지 않는다(`--force`).

- 기준 책: 어린이 8(같은 지은이·시리즈의 책이 장서에 있는 책 4, 없는 책 4), 일반 12(6, 6).
  ISBN 없는 책이 2권 이상 들게 한다.
- 최근 기록: 책 2~3권 목록 10개. 같은 분야 4, 분야가 섞인 것 3, 어린이 3. 이 대화에서 찾은·고른
  책을 흉내 낸다(익명).
- 조정·확인: 묶음마다 세 번째 항목을 확인으로 둔다.
"""

import argparse
import asyncio
import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.central.models import Book
from app.core.config import get_settings
from app.features.children.service import children_book_ids
from app.library.models.catalog import LibraryBook
from app.library.models.library import Library
from app.library.recommendation.authors import writer_keys_sql
from app.library.recommendation.search import recommendable_ids
from app.seed.experiment import LIBRARY_NAME, CollectionMissingError
from evals.collection.fetch import DATA_FILE as COLLECTION_FILE
from evals.recommendation.keys import HOLDOUT_FIELDS, library_keys, load_fields
from evals.recommendation.sets import SEEDS_FILE, parse_seeds

SEED_PLAN = ((True, True, 4), (True, False, 4), (False, True, 6), (False, False, 6))
MIN_WITHOUT_ISBN = 2
HISTORY_MAX = 3  # 최근 기록 한 목록의 최대 권수
HISTORY_PLAN = ("same", "same", "same", "same", "mixed", "mixed", "mixed") + ("children",) * 3


@dataclass(frozen=True)
class BookInfo:
    key: str
    field: str
    children: bool
    related: bool  # 같은 지은이나 같은 시리즈의 다른 책이 장서에 있다


def _order(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _split(position: int) -> str:
    return "check" if position % 3 == 2 else "tune"


def pick(books: Sequence[BookInfo]) -> dict:
    """기준 책과 최근 기록을 고른다. 같은 책 목록이면 늘 같은 결과다."""
    pool = sorted((b for b in books if b.field not in HOLDOUT_FIELDS), key=lambda b: _order(b.key))
    seeds: list[BookInfo] = []
    for children, related, count in SEED_PLAN:
        group = [b for b in pool if b.children == children and b.related == related]
        seeds += group[:count]
    # ISBN 없는 책이 모자라면, 묶음이 같은 ISBN 없는 책으로 뒤에서부터 바꾼다
    without = [b for b in seeds if b.key.startswith("acc:")]
    spare = [b for b in pool if b.key.startswith("acc:") and b not in seeds]
    for i in range(len(seeds) - 1, -1, -1):
        if len(without) >= MIN_WITHOUT_ISBN or not spare:
            break
        old = seeds[i]
        if old.key.startswith("acc:"):
            continue
        swap = next(
            (b for b in spare if (b.children, b.related) == (old.children, old.related)), None
        )
        if swap is not None:
            seeds[i] = swap
            spare.remove(swap)
            without.append(swap)
    similar = [
        {"id": f"s{n:02d}", "book": book.key, "split": _split(n - 1)}
        for n, book in enumerate(seeds, start=1)
    ]

    used = {book.key for book in seeds}
    rest = [b for b in pool if b.key not in used]
    by_field: dict[str, list[BookInfo]] = {}
    for book in rest:
        by_field.setdefault(book.field, []).append(book)
    # 일반 도서가 한 목록(3권)을 채울 만큼 있는 분야만 쓴다
    general_fields = sorted(
        (f for f, group in by_field.items() if sum(not b.children for b in group) >= HISTORY_MAX),
        key=_order,
    )
    history = []
    taken: set[str] = set()

    def take(candidates: Sequence[BookInfo], count: int) -> list[str]:
        chosen = [b.key for b in candidates if b.key not in taken][:count]
        taken.update(chosen)
        return chosen

    for n, kind in enumerate(HISTORY_PLAN, start=1):
        size = 2 + n % 2  # 2권과 3권을 번갈아
        if kind == "same":
            field = general_fields[(n - 1) % len(general_fields)]
            keys = take([b for b in by_field[field] if not b.children], size)
        elif kind == "mixed":
            keys = []
            for step in range(size):
                field = general_fields[(n + step * 3) % len(general_fields)]
                keys += take([b for b in by_field[field] if not b.children], 1)
        else:
            keys = take([b for b in rest if b.children], size)
        if keys:
            history.append({"id": f"h{n:02d}", "books": keys, "split": _split(n - 1)})
    return {"version": 1, "similar": similar, "history": history}


async def book_infos(
    session: AsyncSession, library_id: int, fields: Mapping[str, str]
) -> list[BookInfo]:
    """실험 기관의 추천 가능한 책을 분야, 어린이 구분, 같은 지은이·시리즈 유무와 함께."""
    key_ids = await library_keys(session, library_id)
    recommendable = set(await session.scalars(recommendable_ids(library_id)))
    children = set(await session.scalars(children_book_ids(library_id)))
    rows = await session.execute(
        select(LibraryBook.id, writer_keys_sql(), Book.series_keys)
        .outerjoin(Book, Book.id == LibraryBook.book_id)
        .where(LibraryBook.library_id == library_id, LibraryBook.id.in_(recommendable))
    )
    groups = {
        i: {*(authors or []), *(f"s:{k}" for k in series or [])} for i, authors, series in rows
    }
    counts: dict[str, int] = {}
    for names in groups.values():
        for name in names:
            counts[name] = counts.get(name, 0) + 1
    return [
        BookInfo(
            key=key,
            field=fields[key],
            children=book_id in children,
            related=any(counts[name] > 1 for name in groups.get(book_id, ())),
        )
        for key, book_id in sorted(key_ids.items())
        if book_id in recommendable and key in fields
    ]


def _save(path: Path, document: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=1), encoding="utf-8")


async def run(path: Path = SEEDS_FILE) -> int:
    try:
        fields = load_fields(COLLECTION_FILE)
    except CollectionMissingError as exc:
        print(f"{exc}\n`uv run python -m evals.collection.fetch`로 받은 파일이 필요합니다.")
        return 1
    engine = create_async_engine(get_settings().database_url, poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            library_id = await session.scalar(
                select(Library.id).where(Library.name == LIBRARY_NAME)
            )
            if library_id is None:
                print("실험 기관이 없습니다. `uv run python scripts/seed_experiment.py`")
                return 1
            document = pick(await book_infos(session, library_id, fields))
    finally:
        await engine.dispose()
    parse_seeds(document, fields)  # 남겨 둔 분야가 섞이지 않았는지 다시 본다
    _save(path, document)
    print(f"기준 책 {len(document['similar'])}권, 최근 기록 {len(document['history'])}개: {path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.recommendation.pick")
    parser.add_argument("--force", action="store_true", help="있는 파일을 덮어쓴다")
    args = parser.parse_args()
    if SEEDS_FILE.exists() and not args.force:
        print(f"이미 있습니다: {SEEDS_FILE}\n고친 파일이 기준입니다. 다시 고르려면 --force.")
        return 1
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
