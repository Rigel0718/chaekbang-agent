"""라벨 도구. 사람이 책 목록이나 카드를 보고 어울림 라벨 0·1·2를 단다. LLM을 쓰지 않는다.

    uv run python -m evals.recommendation.label topic              # 실행 전: 관련 분야의 책 (목록)
    uv run python -m evals.recommendation.label topic --cards      # 실행 전을 한 권씩
    uv run python -m evals.recommendation.label similar
    uv run python -m evals.recommendation.label history
    uv run python -m evals.recommendation.label topic --pool <실행 폴더> --variants a,b   # 보충

- 실행 전 단계는 어떤 변형의 결과도 보지 않고 후보를 정한다. 주제 질의는 관련 분야의 추천 가능한
  책(어린이 요청은 어린이 도서만), 비슷한 책·최근 기록은 기준 책들의 분야와 같은 지은이·같은
  시리즈의 책이다. 이 단계를 끝낸 뒤에 실험을 돌린다.
- 보충 단계는 한 실행의 변형들의 상위 10권 중 라벨이 없는 책만 묻는다.
- 목록 방식(실행 전 기본): 항목의 후보를 번호 목록 하나로 보고 2인 번호와 1인 번호만 넣는다.
  확인하면 나머지는 0으로 한 번에 쓴다. `?번호`는 그 책의 카드, r은 다시, q는 끝내기(그 항목은
  쓰지 않는다).
- 카드 방식(보충, 또는 --cards): 한 권씩 묻고 답할 때마다 쓴다. Enter는 0, q는 끝내기.
- 다시 열면 라벨 없는 책부터 이어 간다.
- 라벨 기준: 2 = 받으면 바로 납득, 1 = 관련은 있으나 일부만 맞음, 0 = 맞지 않음.
"""

import argparse
import asyncio
import json
import re
import sys
from collections.abc import Callable, Mapping, Sequence
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
from app.library.recommendation.authors import same_author_books
from app.library.recommendation.cards import shelf_of
from app.library.recommendation.related import editions_of
from app.library.recommendation.search import get_candidates, recommendable_ids
from app.seed.experiment import LIBRARY_NAME, CollectionMissingError
from evals.collection.fetch import DATA_FILE as COLLECTION_FILE
from evals.recommendation.keys import DATA_DIR, library_keys, load_fields
from evals.recommendation.labels import BEFORE, POOL, Labels, labels_file
from evals.recommendation.sets import SEEDS_FILE, TopicQuery, load_seeds, load_topic

DESCRIPTION_LENGTH = 300
LINE_DESCRIPTION_LENGTH = 80
POOL_DEPTH = 10
QUIT = "q"
REDO = "r"
LOOK = "?"
SETS = ("topic", "similar", "history")


@dataclass(frozen=True)
class Card:
    key: str
    title: str
    author: str
    category: str
    shelf: str
    description: str

    def text(self) -> str:
        return (
            f"  {self.title}\n  {self.author} | {self.category or '분류 없음'}"
            f" | {self.shelf or '서가 없음'}\n  {self.description or '(소개 없음)'}"
        )

    def line(self, number: int) -> str:
        return (
            f"{number:>3}. {self.title} / {self.author} | {self.category or '분류 없음'}"
            f" | {self.shelf or '서가 없음'}\n"
            f"     {self.description[:LINE_DESCRIPTION_LENGTH] or '(소개 없음)'}"
        )


Ask = Callable[[str], str]
Show = Callable[[str], None]


def label_item(
    labels: Labels,
    item_id: str,
    heading: str,
    cards: Sequence[Card],
    stage: str,
    *,
    ask: Ask = input,
    show: Show = print,
) -> bool:
    """항목 하나의 라벨 없는 책을 차례로 묻는다. 끝내기를 고르면 False를 돌려준다."""
    todo = [card for card in cards if labels.grade(item_id, card.key) is None]
    for number, card in enumerate(todo, start=1):
        show(f"\n[{item_id}] {heading}  ({number}/{len(todo)})\n{card.text()}")
        while True:
            answer = ask("라벨 0·1·2 (Enter=0, q=끝내기): ").strip()
            if answer == QUIT:
                return False
            if answer in ("", "0", "1", "2"):
                labels.put(item_id, card.key, int(answer or 0), stage)
                break
            show("0, 1, 2 중 하나를 입력하세요.")
    return True


def _ask_numbers(prompt: str, cards: Sequence[Card], ask: Ask, show: Show) -> list[int] | None:
    """번호들을 받는다(공백·쉼표로 나눔). 끝내기면 None. 잘못된 값이면 다시 묻는다."""
    while True:
        answer = ask(prompt).strip()
        if answer == QUIT:
            return None
        tokens = [token for token in re.split(r"[\s,]+", answer.removeprefix(LOOK)) if token]
        if not all(token.isdigit() and 1 <= int(token) <= len(cards) for token in tokens):
            show(f"1~{len(cards)} 사이의 번호를 넣으세요.")
            continue
        numbers = sorted({int(token) for token in tokens})
        if not answer.startswith(LOOK):
            return numbers
        for number in numbers:
            show(f"\n{number}.\n{cards[number - 1].text()}")


def label_list(
    labels: Labels,
    item_id: str,
    heading: str,
    cards: Sequence[Card],
    stage: str,
    *,
    ask: Ask = input,
    show: Show = print,
) -> bool:
    """항목 하나의 라벨 없는 책을 목록으로 보이고 2·1인 번호를 받는다. 나머지는 0이다.

    확인해야 쓴다(한 번에). 끝내기를 고르면 그 항목은 쓰지 않고 False를 돌려준다.
    """
    todo = [card for card in cards if labels.grade(item_id, card.key) is None]
    if not todo:
        return True
    listing = "\n".join(card.line(number) for number, card in enumerate(todo, start=1))
    show(f"\n[{item_id}] {heading}  ({len(todo)}권)\n{listing}")
    while True:
        show(f"\n[{item_id}] {heading}")
        twos = _ask_numbers("2인 번호 (없으면 Enter, ?번호=카드 보기, q=끝내기): ", todo, ask, show)
        if twos is None:
            return False
        ones = _ask_numbers("1인 번호 (없으면 Enter): ", todo, ask, show)
        if ones is None:
            return False
        both = sorted(set(twos) & set(ones))
        if both:
            show(f"2와 1에 모두 든 번호가 있습니다: {both}. 다시 넣으세요.")
            continue
        for grade, numbers in ((2, twos), (1, ones)):
            for number in numbers:
                show(f"  {grade} ← {number}. {todo[number - 1].title}")
        show(f"  나머지 {len(todo) - len(twos) - len(ones)}권은 0")
        answer = ask("확인(Enter) / 다시(r) / 끝내기(q): ").strip()
        if answer == QUIT:
            return False
        if answer == "":
            grades = {card.key: 0 for card in todo}
            grades.update({todo[number - 1].key: 2 for number in twos})
            grades.update({todo[number - 1].key: 1 for number in ones})
            labels.put_many(item_id, grades, stage)
            return True


async def cards_for(
    session: AsyncSession,
    library_id: int,
    ids: Sequence[int],
    keys: Mapping[int, str],
    length: int | None = DESCRIPTION_LENGTH,
) -> list[Card]:
    """기관 도서 id 순서대로 카드를 만든다. 표시 값은 공식 값을 먼저 쓴다.

    length가 None이면 소개 전문이다.
    """
    candidates = await get_candidates(session, library_id, list(ids))
    shelves = await shelf_of(session, library_id, list(ids))
    categories = dict(
        (
            await session.execute(
                select(LibraryBook.id, Book.external_category)
                .join(Book, Book.id == LibraryBook.book_id)
                .where(LibraryBook.library_id == library_id, LibraryBook.id.in_(list(ids)))
            )
        ).all()
    )
    cards = []
    for book_id in ids:
        book = candidates[book_id].library_book
        description = " ".join((book.shown("description") or "").split())
        cards.append(
            Card(
                key=keys[book_id],
                title=book.shown("title"),
                author=book.shown("author") or "",
                category=categories.get(book_id) or "",
                shelf=shelves.get(book_id, (None, None))[0] or "",
                description=description[:length],
            )
        )
    return cards


async def topic_candidates(
    session: AsyncSession,
    library_id: int,
    query: TopicQuery,
    fields: Mapping[str, str],
    key_ids: Mapping[str, int],
) -> list[int]:
    """실행 전 후보: 관련 분야의 추천 가능한 책. 어린이 요청이면 어린이 도서만."""
    allowed = set(await session.scalars(recommendable_ids(library_id)))
    if query.children:
        allowed &= set(await session.scalars(children_book_ids(library_id)))
    return sorted(
        book_id
        for key, book_id in key_ids.items()
        if fields.get(key) in query.fields and book_id in allowed
    )


async def related_candidates(
    session: AsyncSession,
    library_id: int,
    base_keys: Sequence[str],
    fields: Mapping[str, str],
    key_ids: Mapping[str, int],
) -> list[int]:
    """실행 전 후보: 기준 책들의 분야 + 같은 지은이·같은 시리즈의 책.

    기준 책과 그 다른 판본은 뺀다. 기준 책이 모두 어린이 도서이면 어린이 도서만 후보다(실행할 때
    어린이 도서 조건을 거는 기준과 같다).
    """
    base_ids = [key_ids[key] for key in base_keys if key in key_ids]
    base_fields = {fields.get(key) for key in base_keys}
    allowed = set(await session.scalars(recommendable_ids(library_id)))
    children = set(await session.scalars(children_book_ids(library_id)))
    if base_ids and all(base_id in children for base_id in base_ids):
        allowed &= children
    found = {
        book_id
        for key, book_id in key_ids.items()
        if fields.get(key) in base_fields and book_id in allowed
    }
    for base_id in base_ids:
        found |= {book.id for book in await same_author_books(session, library_id, base_id)}
    series = await session.execute(
        select(LibraryBook.id, Book.series_keys)
        .join(Book, Book.id == LibraryBook.book_id)
        .where(LibraryBook.library_id == library_id, LibraryBook.id.in_(allowed))
    )
    by_id = {book_id: set(keys) for book_id, keys in series}
    wanted = set().union(*(by_id.get(base_id, set()) for base_id in base_ids))
    found |= {book_id for book_id, keys in by_id.items() if keys & wanted}
    hidden = {*base_ids, *(await editions_of(session, library_id, base_ids))}
    return sorted((found & allowed) - hidden)


def pool_keys(
    results: Mapping[str, Mapping[str, Sequence[Mapping]]],
    variants: Sequence[str],
    labels: Labels,
    depth: int = POOL_DEPTH,
) -> dict[str, list[str]]:
    """실행 결과(`results.json`의 변형 → 항목 → 순위)에서 항목별로 라벨 없는 책 키를 모은다."""
    pooled: dict[str, list[str]] = {}
    for variant in variants:
        for item_id, ranked in results[variant].items():
            for row in ranked[:depth]:
                seen = pooled.setdefault(item_id, [])
                if labels.grade(item_id, row["key"]) is None and row["key"] not in seen:
                    seen.append(row["key"])
    return {item_id: keys for item_id, keys in pooled.items() if keys}


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


async def run(set_name: str, pool: Path | None, variants: Sequence[str], cards: bool) -> int:
    settings = get_settings()
    try:
        fields = load_fields(COLLECTION_FILE)
    except CollectionMissingError as exc:
        print(f"{exc}\n`uv run python -m evals.collection.fetch`로 받은 파일이 필요합니다.")
        return 1
    labels = Labels(labels_file(set_name))
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            library_id = await session.scalar(
                select(Library.id).where(Library.name == LIBRARY_NAME)
            )
            if library_id is None:
                print("실험 기관이 없습니다. `uv run python scripts/seed_experiment.py`")
                return 1
            key_ids = await library_keys(session, library_id)
            id_keys = {book_id: key for key, book_id in key_ids.items()}
            items: list[tuple[str, str, list[int]]] = []  # (항목 id, 머리글, 후보 id)
            if set_name == "topic":
                for query in load_topic():
                    heading = f"{query.text}" + ("  [어린이 요청]" if query.children else "")
                    ids = await topic_candidates(session, library_id, query, fields, key_ids)
                    items.append((query.id, heading, ids))
            else:
                seeds, histories = load_seeds(fields, SEEDS_FILE)
                rows = (
                    [(seed.id, [seed.book]) for seed in seeds]
                    if set_name == "similar"
                    else [(history.id, list(history.books)) for history in histories]
                )
                for item_id, base in rows:
                    base_cards = await cards_for(
                        session, library_id, [key_ids[key] for key in base], id_keys
                    )
                    heading = "이 책을 좋게 읽은 사람에게 권할 책인가\n" + "\n".join(
                        f"  ▶ {card.title} / {card.author}\n    {card.description[:120]}"
                        for card in base_cards
                    )
                    ids = await related_candidates(session, library_id, base, fields, key_ids)
                    items.append((item_id, heading, ids))
            stage = BEFORE
            if pool is not None:
                stage = POOL
                wanted = pool_keys(_read_json(pool / "results.json"), variants, labels)
                items = [
                    (
                        item_id,
                        heading,
                        [key_ids[k] for k in wanted.get(item_id, []) if k in key_ids],
                    )
                    for item_id, heading, _ in items
                ]
            total = sum(
                1
                for item_id, _, ids in items
                for i in ids
                if labels.grade(item_id, id_keys[i]) is None
            )
            print(f"{set_name} {stage} 단계: 라벨 없는 책 {total}건. 파일 {labels.path}")
            for item_id, heading, ids in items:
                ask_item = label_item if cards or pool is not None else label_list
                item_cards = await cards_for(session, library_id, ids, id_keys)
                if not ask_item(labels, item_id, heading, item_cards, stage):
                    break
            print(f"단계별 라벨 수: {labels.stage_counts()}")
    finally:
        await engine.dispose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.recommendation.label")
    parser.add_argument("set", choices=SETS, help="라벨을 달 세트")
    parser.add_argument("--pool", type=Path, help="보충할 실행 폴더(없으면 실행 전 단계)")
    parser.add_argument("--variants", default="", help="보충에 쓸 변형 이름(쉼표로)")
    parser.add_argument(
        "--cards", action="store_true", help="실행 전 단계도 한 권씩 묻는다(기본은 목록)"
    )
    args = parser.parse_args()
    pool = args.pool
    if pool is not None and not pool.is_absolute() and not pool.exists():
        pool = DATA_DIR / "runs" / pool
    variants = [name for name in args.variants.split(",") if name]
    if pool is not None and not variants:
        parser.error("--pool에는 --variants가 필요합니다")
    return asyncio.run(run(args.set, pool, variants, args.cards))


if __name__ == "__main__":
    sys.exit(main())
