"""라벨 초안. Claude가 대화에서 후보를 읽고 단 0·1·2를 라벨 파일에 넣는다.

외부 LLM API를 부르지 않는다.

    uv run python -m evals.recommendation.draft dump topic            # 후보를 data/draft/에 쓴다
    uv run python -m evals.recommendation.draft apply topic <초안.json>
    uv run python -m evals.recommendation.draft dump similar          # history도 같다

- 초안은 어떤 변형의 결과도 보지 않고 실행 전 후보 전체에 단다.
- 초안 파일은 `{"t01": {"<책 키>": 2, …}}`로 1 이상인 책만 적는다. 적지 않은 후보는 0이다.
- 사람이 단 라벨(`by`가 `user`)은 덮어쓰지 않는다. 검수는 `evals.recommendation.review`.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.features.children.service import children_book_ids
from app.library.models.library import Library
from app.seed.experiment import LIBRARY_NAME
from evals.collection.fetch import DATA_FILE as COLLECTION_FILE
from evals.recommendation.keys import DATA_DIR, library_keys, load_fields
from evals.recommendation.label import (
    Card,
    cards_for,
    pool_keys,
    related_candidates,
    topic_candidates,
)
from evals.recommendation.labels import BEFORE, CLAUDE, POOL, USER, Labels, labels_file
from evals.recommendation.sets import TopicQuery, load_seeds, load_topic

DRAFT_DIR = DATA_DIR / "draft"
SETS = ("topic", "similar", "history")


@dataclass(frozen=True)
class RelatedItem:
    """비슷한 책의 기준 책 하나, 또는 최근 기록 하나. 초안과 검수 화면이 주제 질의처럼 다룬다."""

    id: str
    text: str  # 머리글: 기준 책(들)의 서명
    children: bool  # 기준 책이 모두 어린이 도서다
    split: str
    bases: tuple[Card, ...]  # 기준 책(들)의 카드(소개 전문)


class DraftError(ValueError):
    pass


def apply_draft(
    labels: Labels, item_id: str, candidates: Sequence[str], picks: Mapping[str, int]
) -> int:
    """한 항목의 초안을 넣는다. 후보 전체에 달고(적지 않은 책은 0) 사람 라벨은 그대로 둔다.

    넣은 라벨 수를 돌려준다. 후보가 아닌 책 키가 초안에 있으면 오류다.
    """
    unknown = sorted(set(picks) - set(candidates))
    if unknown:
        raise DraftError(f"{item_id}: 후보가 아닌 책 키 {unknown}")
    grades = {key: picks.get(key, 0) for key in candidates if labels.labeler(item_id, key) != USER}
    if grades:
        labels.put_many(item_id, grades, BEFORE, CLAUDE)
    return len(grades)


def apply_pool_draft(
    labels: Labels, item_id: str, pool: Sequence[str], picks: Mapping[str, int]
) -> int:
    """한 항목의 보충 초안을 넣는다. 라벨이 없는 보충 책에만 단다(적지 않은 책은 0)."""
    unknown = sorted(set(picks) - set(pool))
    if unknown:
        raise DraftError(f"{item_id}: 보충 목록에 없는 책 키 {unknown}")
    grades = {key: picks.get(key, 0) for key in pool if labels.grade(item_id, key) is None}
    if grades:
        labels.put_many(item_id, grades, POOL, CLAUDE)
    return len(grades)


async def load_topic_items(
    database_url: str,
    length: int | None,
    extra: Mapping[str, Sequence[str]] | None = None,
    holdout: bool = False,
) -> list[tuple[TopicQuery, list[Card]]]:
    """주제 질의마다 실행 전 후보의 카드. 실험 기관이 없으면 빈 목록.

    extra(질의 id → 책 키)가 있으면 후보 밖의 그 책들(보충 라벨)도 뒤에 붙인다.
    """
    fields = load_fields(COLLECTION_FILE)
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            library_id = await session.scalar(
                select(Library.id).where(Library.name == LIBRARY_NAME)
            )
            if library_id is None:
                return []
            key_ids = await library_keys(session, library_id)
            id_keys = {book_id: key for key, book_id in key_ids.items()}
            items = []
            for query in load_topic(holdout=holdout):
                ids = await topic_candidates(session, library_id, query, fields, key_ids)
                more = sorted(
                    {key_ids[k] for k in (extra or {}).get(query.id, ()) if k in key_ids} - set(ids)
                )
                ids = [*ids, *more]
                items.append((query, await cards_for(session, library_id, ids, id_keys, length)))
            return items
    finally:
        await engine.dispose()


async def load_related_items(
    database_url: str,
    set_name: str,
    length: int | None,
    extra: Mapping[str, Sequence[str]] | None = None,
    holdout: bool = False,
) -> list[tuple[RelatedItem, list[Card]]]:
    """비슷한 책(`similar`)이나 최근 기록(`history`) 항목마다 실행 전 후보의 카드.

    후보는 기준 책들의 분야 + 같은 지은이·같은 시리즈의 책이다(다른 판본 제외, 어린이 기준 책이면
    어린이 도서만). extra가 있으면 후보 밖의 그 책들(보충 라벨)도 뒤에 붙인다.
    """
    fields = load_fields(COLLECTION_FILE)
    seeds, histories = load_seeds(fields, holdout=holdout)
    rows = (
        [(seed.id, seed.split, [seed.book]) for seed in seeds]
        if set_name == "similar"
        else [(history.id, history.split, list(history.books)) for history in histories]
    )
    engine = create_async_engine(database_url, poolclass=NullPool)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            library_id = await session.scalar(
                select(Library.id).where(Library.name == LIBRARY_NAME)
            )
            if library_id is None:
                return []
            key_ids = await library_keys(session, library_id)
            id_keys = {book_id: key for key, book_id in key_ids.items()}
            children = set(await session.scalars(children_book_ids(library_id)))
            items = []
            for item_id, split, base_keys in rows:
                base_ids = [key_ids[key] for key in base_keys]
                bases = await cards_for(session, library_id, base_ids, id_keys, None)
                ids = await related_candidates(session, library_id, base_keys, fields, key_ids)
                more = sorted(
                    {key_ids[k] for k in (extra or {}).get(item_id, ()) if k in key_ids}
                    - set(ids)
                    - set(base_ids)
                )
                item = RelatedItem(
                    id=item_id,
                    text=" + ".join(card.title for card in bases),
                    children=all(base_id in children for base_id in base_ids),
                    split=split,
                    bases=tuple(bases),
                )
                cards = await cards_for(session, library_id, [*ids, *more], id_keys, length)
                items.append((item, cards))
            return items
    finally:
        await engine.dispose()


async def load_items(
    database_url: str,
    set_name: str,
    length: int | None,
    extra: Mapping[str, Sequence[str]] | None = None,
    holdout: bool = False,
) -> list:
    """세트의 (항목, 후보 카드) 목록. 실험 기관이 없으면 빈 목록. holdout은 남겨 둔 분야 세트."""
    if set_name == "topic":
        return await load_topic_items(database_url, length, extra, holdout)
    return await load_related_items(database_url, set_name, length, extra, holdout)


def _line(card: Card, length: int | None) -> str:
    return (
        f"{card.key} | {card.title} | {card.author} | {card.category} | {card.description[:length]}"
    )


def _dump_related(
    set_name: str, items: Sequence[tuple[RelatedItem, Sequence[Card]]], length: int
) -> None:
    """기준 책·기록의 후보를 쓴다. 책은 한 번만(`<세트>-books.txt`), 항목마다 후보 키만 쓴다.

    여러 항목이 같은 분야의 책을 되풀이해 후보로 가져서, 책 소개를 한 번만 읽게 한다.
    """
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    books: dict[str, Card] = {}
    lines = []
    for item, cards in items:
        lines += ["", f"# {item.id} [{item.split}]" + (" [어린이]" if item.children else "")]
        lines += [f"기준: {_line(base, None)}" for base in item.bases]
        lines.append(f"후보 {len(cards)}권: " + " ".join(card.key for card in cards))
        books.update({card.key: card for card in cards})
    path = DRAFT_DIR / f"{set_name}-items.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{path} ({len(items)}개 항목, 후보 {sum(len(cards) for _, cards in items)}건)")
    ordered = sorted(books.values(), key=lambda card: (card.category, card.title, card.key))
    path = DRAFT_DIR / f"{set_name}-books.txt"
    path.write_text("\n".join(_line(card, length) for card in ordered) + "\n", encoding="utf-8")
    print(f"{path} (책 {len(books)}권)")


def _dump(
    items: Sequence[tuple[TopicQuery, Sequence[Card]]], length: int, prefix: str = ""
) -> None:
    """후보를 같은 후보 묶음끼리 한 파일로 쓴다(어린이 질의는 같은 책을 되풀이해 본다)."""
    DRAFT_DIR.mkdir(parents=True, exist_ok=True)
    groups: dict[tuple[str, ...], list[TopicQuery]] = {}
    cards_of: dict[tuple[str, ...], Sequence[Card]] = {}
    for query, cards in items:
        group = ("children" if query.children else "general", *sorted(query.fields))
        groups.setdefault(group, []).append(query)
        cards_of[group] = cards
    for group, queries in groups.items():
        lines = [f"# {' '.join(group)} ({len(cards_of[group])}권)", ""]
        lines += [f"- {q.id} [{q.split}] {q.text}" for q in queries]
        lines.append("")
        for card in cards_of[group]:
            lines.append(
                f"{card.key} | {card.title} | {card.author} | {card.category} | "
                f"{card.description[:length]}"
            )
        path = DRAFT_DIR / f"{prefix}{'-'.join(group)}.txt"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"{path} ({len(queries)}개 질의, {len(cards_of[group])}권)")


def _pool(
    args: argparse.Namespace,
    items: Sequence[tuple[TopicQuery, Sequence[Card]]],
    wanted: Mapping[str, Sequence[str]],
    labels: Labels,
) -> int:
    """보충: 라벨 없는 상위 결과를 파일로 쓰거나(dump), 그 초안을 넣는다(apply)."""
    if args.command == "dump":
        DRAFT_DIR.mkdir(parents=True, exist_ok=True)
        lines = []
        for query, cards in items:
            pool = [card for card in cards if card.key in set(wanted.get(query.id, ()))]
            if not pool:
                continue
            lines += ["", f"# {query.id} {query.text}" + (" [어린이]" if query.children else "")]
            lines += [f"기준: {_line(base, None)}" for base in getattr(query, "bases", ())]
            lines += [
                f"{card.key} | {card.title} | {card.author} | {card.category} | "
                f"{card.description[: args.length]}"
                for card in pool
            ]
        prefix = "holdout-" if args.holdout else ""
        path = DRAFT_DIR / f"{prefix}{args.set}-pool.txt"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"{path} (라벨 없는 책 {sum(len(keys) for keys in wanted.values())}건)")
        return 0
    picks = json.loads(args.file.read_text(encoding="utf-8"))
    for item_id, grades in picks.items():  # 쓰기 전에 모두 검사한다
        stray = sorted(set(grades) - set(wanted.get(item_id, ())))
        if stray:
            print(f"{item_id}: 보충 목록에 없는 책 키 {stray}")
            return 1
    total = sum(
        apply_pool_draft(labels, item_id, keys, picks.get(item_id, {}))
        for item_id, keys in wanted.items()
    )
    print(f"보충 초안 {total}건. 단계별 {labels.stage_counts()}, 단 쪽별 {labels.by_counts()}")
    return 0


CONVERSATION_RUNS = Path(__file__).parent.parent / "conversation" / "data" / "runs"


def read_pool_results(pool: Path, set_name: str) -> dict:
    """보충할 실행 결과. 실험 실행은 `results.json`, 대화 추천 평가 실행은 세트마다
    `results-<세트>.json`(변형 `chat`)이다. 폴더 이름만 주면 두 실행 폴더에서 찾는다."""
    run = next(
        (p for p in (pool, DATA_DIR / "runs" / pool, CONVERSATION_RUNS / pool) if p.exists()), pool
    )
    path = run / f"results-{set_name}.json"
    if not path.exists():
        path = run / "results.json"
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m evals.recommendation.draft")
    commands = parser.add_subparsers(dest="command", required=True)
    dump = commands.add_parser("dump", help="후보를 data/draft/에 쓴다")
    dump.add_argument("set", choices=SETS)
    dump.add_argument("--length", type=int, default=400, help="소개 글자 수")
    apply = commands.add_parser("apply", help="초안 파일을 라벨 파일에 넣는다")
    apply.add_argument("set", choices=SETS)
    apply.add_argument("file", type=Path)
    for command in (dump, apply):
        command.add_argument("--pool", type=Path, help="보충: 실행 폴더(상위 10권 중 라벨 없는 책)")
        command.add_argument("--variants", default="", help="보충에 쓸 변형 이름(쉼표로)")
        command.add_argument("--holdout", action="store_true", help="남겨 둔 분야 세트")
    args = parser.parse_args()

    labels = Labels(labels_file(args.set, args.holdout))
    wanted: dict[str, list[str]] = {}
    if args.pool is not None:
        results = read_pool_results(args.pool, args.set)
        names = [name for name in args.variants.split(",") if name] or list(results)
        wanted = pool_keys(results, names, labels)
    items = asyncio.run(
        load_items(get_settings().database_url, args.set, None, wanted, args.holdout)
    )
    if not items:
        print("실험 기관이 없습니다. `uv run python scripts/seed_experiment.py`")
        return 1
    if args.pool is not None:
        return _pool(args, items, wanted, labels)
    if args.command == "dump":
        prefix = "holdout-" if args.holdout else ""
        if args.set == "topic":
            _dump(items, args.length, prefix)
        else:
            _dump_related(f"{prefix}{args.set}", items, args.length)
        return 0
    picks = json.loads(args.file.read_text(encoding="utf-8"))
    unknown = sorted(set(picks) - {query.id for query, _ in items})
    if unknown:
        print(f"없는 항목 id: {unknown}")
        return 1
    for query, cards in items:  # 쓰기 전에 모두 검사한다
        stray = sorted(set(picks.get(query.id, {})) - {card.key for card in cards})
        if stray:
            print(f"{query.id}: 후보가 아닌 책 키 {stray}")
            return 1
    try:
        for query, cards in items:
            count = apply_draft(
                labels, query.id, [card.key for card in cards], picks.get(query.id, {})
            )
            grades = labels.grades(query.id)
            print(
                f"{query.id}: 초안 {count}건 (2: {sum(g == 2 for g in grades.values())},"
                f" 1: {sum(g == 1 for g in grades.values())}, 전체 {len(grades)})"
            )
    except DraftError as exc:
        print(exc)
        return 1
    print(f"단 쪽별 라벨 수: {labels.by_counts()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
