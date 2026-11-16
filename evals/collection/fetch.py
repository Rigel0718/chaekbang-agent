"""YES24 실험 장서를 받는다: uv run python -m evals.collection.fetch [--dry-run]

분야 구성(`plan.py`)대로 카테고리 스테디셀러를 받아 원본 상품을 파일 하나로 남긴다. 받은 날짜,
분야마다의 카테고리·목표·받은 권수·거른 건수, 책마다 어느 분야에서 왔는지를 함께 적는다.
개발 DB에 넣는 것은 `scripts/seed_experiment.py`다.

소장 도서의 ISBN만 조회한다는 YES24 규칙의 예외다(평가 표본과 같은 예외). **한 번만 받는다.**
파일이 있으면 외부를 부르지 않고 멈춘다. 파일은 저장소에 넣지 않는다(`.gitignore`). 판매가,
판매 상태, 포인트, 판매지수, 평점은 파일에도 넣지 않는다. 서비스 경로에서 쓰지 않는다.
종료 코드: 0 완료, 1 전제 조건(키 없음, 파일 있음), 2 외부 장애로 중단(파일을 쓰지 않는다).

받은 기록: 2026-11-15, 카테고리 스테디셀러(`detail=Y`, 분야마다 1쪽, 호출 19회), 525권. 다시 받지
않는 이유는 둘이다. 이용 조건의 예외를 한 번으로 묶어 두고, 같은 날 같은 방식으로 받은 장서여야
실험끼리 비교된다. `add-bibliographic-sources`(2026-11-16)에서도 지우지 않는다. 같은 ISBN의
정보나루·카카오 값은 `evals/collection/sources.py`가 따로 받아 둔다.
"""

import argparse
import asyncio
import json
import math
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.central.external.yes24.category import steady_sellers
from app.central.external.yes24.client import Yes24Client, Yes24Stopped
from app.central.external.yes24.definitions import (
    ADULT_KEY,
    ADULT_YES,
    MAX_PAGE_SIZE,
    REQUEST_TIMEOUT_SECONDS,
    VOLATILE_ITEM_KEYS,
)
from app.central.external.yes24.parsing import parse_item
from app.core import clock
from app.core.config import get_settings
from evals.collection.plan import FIELDS, Field
from evals.librarian.catalog import real_isbn

DATA_FILE = Path(__file__).parent / "data" / "yes24_collection.json"
SAMPLE_FILE = Path(__file__).parents[1] / "librarian" / "data" / "yes24_sample.json"
METHOD = "category/bestsellerSteady"
MAX_PAGES = 3  # 분야마다 쪽(100권) 수 상한. 거르는 상품이 많아도 여기서 멈춘다
NOT_BOOK_CATEGORIES = ("잡지", "전집")  # 분류 원문에 이 낱말이 든 상품은 뺀다

EXIT_OK = 0
EXIT_PRECONDITION = 1
EXIT_STOPPED = 2


class SkipReason:
    NOT_ISBN = "not_isbn"
    NO_TITLE_AUTHOR = "no_title_author"
    NOT_BOOK = "not_book"  # 잡지·전집
    ADULT = "adult"
    DUPLICATE = "duplicate"  # 앞 분야에서 이미 받음


@dataclass
class FieldRecord:
    key: str
    name: str
    category_id: str
    target: int
    holdout: bool
    fetched: int = 0
    pages: int = 0
    total_count: int = 0  # 외부가 알려 준 그 카테고리의 전체 수
    skipped: dict[str, int] = field(default_factory=dict)


def skip_reason(item: dict[str, Any]) -> str | None:
    """넣지 않는 이유. 넣으면 None."""
    parsed = parse_item(item)
    if real_isbn(parsed.isbn13) is None:
        return SkipReason.NOT_ISBN
    if not parsed.title or not parsed.author:
        return SkipReason.NO_TITLE_AUTHOR
    if parsed.category and any(word in parsed.category for word in NOT_BOOK_CATEGORIES):
        return SkipReason.NOT_BOOK
    if item.get(ADULT_KEY) == ADULT_YES:
        return SkipReason.ADULT
    return None


def strip_volatile(item: dict[str, Any]) -> dict[str, Any]:
    """저장하지 않는 변동 값의 키를 뺀 원본. 다른 값은 그대로 둔다."""
    return {key: value for key, value in item.items() if key not in VOLATILE_ITEM_KEYS}


def expected_calls(fields: tuple[Field, ...] | None = None) -> tuple[int, int]:
    """(예상 호출 수, 최대 호출 수). 거르는 상품이 적으면 분야마다 한 쪽이면 된다."""
    fields = FIELDS if fields is None else fields
    least = sum(math.ceil(f.target / MAX_PAGE_SIZE) for f in fields)
    return least, len(fields) * MAX_PAGES


async def collect(
    client: Yes24Client, fields: tuple[Field, ...] | None = None
) -> tuple[list[FieldRecord], list[dict[str, Any]]]:
    """분야 순서대로 받는다. 같은 ISBN은 먼저 받은 분야에만 넣는다. 외부 장애는 그대로 올린다."""
    fields = FIELDS if fields is None else fields
    seen: set[str] = set()
    records: list[FieldRecord] = []
    books: list[dict[str, Any]] = []
    for plan in fields:
        record = FieldRecord(plan.key, plan.name, plan.category_id, plan.target, plan.holdout)
        skipped: Counter[str] = Counter()
        page = 1
        while record.fetched < plan.target and page <= MAX_PAGES:
            items, total = await steady_sellers(client, plan.category_id, page=page)
            record.pages = page
            record.total_count = total
            for item in items:
                if record.fetched >= plan.target:
                    break
                reason = skip_reason(item)
                isbn = real_isbn(parse_item(item).isbn13)
                if reason is None and isbn in seen:
                    reason = SkipReason.DUPLICATE
                if reason is not None:
                    skipped[reason] += 1
                    continue
                seen.add(isbn)
                record.fetched += 1
                books.append(
                    {"field": plan.key, "rank": record.fetched, "item": strip_volatile(item)}
                )
            if not items or page * MAX_PAGE_SIZE >= total:
                break
            page += 1
        record.skipped = dict(skipped)
        records.append(record)
    return records, books


def document(records: list[FieldRecord], books: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "fetched_on": clock.today().isoformat(),
        "source": "yes24",
        "method": METHOD,
        "fields": [asdict(record) for record in records],
        "books": books,
    }


def sample_isbns(path: Path = SAMPLE_FILE) -> set[str]:
    """평가 표본의 ISBN. 겹친 건수를 출력하는 데만 쓴다. 표본이 없으면 빈 집합."""
    if not path.exists():
        return set()
    rows = json.loads(path.read_text(encoding="utf-8")).get("books", [])
    return {row["isbn13"] for row in rows if row.get("isbn13")}


def report(records: list[FieldRecord], books: list[dict[str, Any]]) -> None:
    for r in records:
        skipped = ", ".join(f"{k} {v}" for k, v in sorted(r.skipped.items())) or "없음"
        holdout = " (남겨 둔 분야)" if r.holdout else ""
        print(
            f"{r.name}{holdout}: {r.fetched}/{r.target}권, {r.pages}쪽, "
            f"카테고리 전체 {r.total_count}, 거름 {skipped}"
        )
    no_description = sum(1 for b in books if not parse_item(b["item"]).description)
    overlap = {parse_item(b["item"]).isbn13 for b in books} & sample_isbns()
    total = Counter[str]()
    for r in records:
        total.update(r.skipped)
    print(
        f"합계 {len(books)}/{sum(r.target for r in records)}권. "
        f"거름 {dict(sorted(total.items()))}. 소개 없음 {no_description}권. "
        f"평가 표본과 겹친 ISBN {len(overlap)}권."
    )


def dry_run() -> int:
    least, most = expected_calls()
    for f in FIELDS:
        holdout = " (남겨 둔 분야)" if f.holdout else ""
        print(f"{f.name} ({f.category_id}){holdout}: 목표 {f.target}권")
    print(
        f"분야 {len(FIELDS)}개, 목표 {sum(f.target for f in FIELDS)}권. "
        f"예상 호출 {least}회 (거르는 상품이 많으면 최대 {most}회). 외부 호출 없음."
    )
    return EXIT_OK


def _write(path: Path, content: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content, ensure_ascii=False, indent=1), encoding="utf-8")


async def fetch(client: Yes24Client, path: Path = DATA_FILE) -> int:
    """받아서 파일로 쓴다. 파일이 있으면 부르지 않는다. 중간에 멈추면 파일을 쓰지 않는다."""
    if Path.exists(path):
        print(f"이미 받은 파일이 있습니다: {path}. 한 번만 받습니다.", file=sys.stderr)
        return EXIT_PRECONDITION
    try:
        records, books = await collect(client)
    except Yes24Stopped as exc:
        print(f"중단: {exc.reason.value}. 파일을 쓰지 않았습니다.", file=sys.stderr)
        return EXIT_STOPPED
    _write(path, document(records, books))
    report(records, books)
    print(f"저장했습니다: {path}")
    return EXIT_OK


async def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="YES24 실험 장서를 분야 구성대로 한 번 받는다")
    parser.add_argument("--dry-run", action="store_true", help="목표와 예상 호출 수만 출력")
    args = parser.parse_args(argv)
    if args.dry_run:
        return dry_run()
    if DATA_FILE.exists():
        print(f"이미 받은 파일이 있습니다: {DATA_FILE}. 한 번만 받습니다.", file=sys.stderr)
        return EXIT_PRECONDITION
    settings = get_settings()
    key = settings.yes24_api_key.get_secret_value() if settings.yes24_api_key else ""
    if not key:
        print("YES24_API_KEY가 없습니다.", file=sys.stderr)
        return EXIT_PRECONDITION
    async with httpx.AsyncClient(
        base_url=settings.yes24_base_url, timeout=REQUEST_TIMEOUT_SECONDS
    ) as http:
        return await fetch(Yes24Client(http, key))


if __name__ == "__main__":
    sys.exit(asyncio.run(run(sys.argv[1:])))
