"""YES24 평가 표본을 받는다. 일회성이고, 파일은 저장소에 넣지 않는다.

소장 도서의 ISBN만 조회한다는 규칙의 예외다. 표본을 늘리거나 주기적으로 받지 않는다.
판매가, 판매 상태, 평점은 저장하지 않는다.
"""

import asyncio
import json
import sys
from dataclasses import asdict
from pathlib import Path

import httpx

from app.central.external.yes24.client import Yes24Client, Yes24Stopped
from app.central.external.yes24.definitions import REQUEST_TIMEOUT_SECONDS
from app.central.external.yes24.goods import search_items
from app.central.external.yes24.parsing import Yes24Item
from app.core import clock
from app.core.config import get_settings

DATA_FILE = Path(__file__).parent / "data" / "yes24_sample.json"
QUERIES = (
    "공룡",
    "그림책",
    "어린이 과학",
    "동화",
    "에세이",
    "소설",
    "역사",
    "요리",
    "자기계발",
    "여행",
)
PER_QUERY = 10
SKIPPED_FIELDS = ("list_price",)


def _row(item: Yes24Item, query: str) -> dict[str, object]:
    row = asdict(item)
    for field in SKIPPED_FIELDS:
        row.pop(field)
    row["published_date"] = item.published_date.isoformat() if item.published_date else None
    row["query"] = query
    return row


async def fetch(client: Yes24Client) -> list[dict[str, object]]:
    """검색어마다 받아 ISBN으로 중복을 뺀다. ISBN과 서명·저자가 없는 상품은 뺀다."""
    rows: dict[str, dict[str, object]] = {}
    for query in QUERIES:
        for item in await search_items(client, query, PER_QUERY):
            if item.isbn13 and item.title and item.author:
                rows.setdefault(item.isbn13, _row(item, query))
    return list(rows.values())


async def run() -> int:
    settings = get_settings()
    key = settings.yes24_api_key.get_secret_value() if settings.yes24_api_key else ""
    if not key:
        print("YES24_API_KEY가 없습니다.", file=sys.stderr)
        return 1
    if DATA_FILE.exists():
        print(f"이미 표본이 있습니다: {DATA_FILE}. 다시 받으려면 먼저 지우세요.", file=sys.stderr)
        return 1
    async with httpx.AsyncClient(
        base_url=settings.yes24_base_url, timeout=REQUEST_TIMEOUT_SECONDS
    ) as http:
        try:
            rows = await fetch(Yes24Client(http, key))
        except Yes24Stopped as exc:
            print(f"중단: {exc.reason.value}", file=sys.stderr)
            return 1
    DATA_FILE.parent.mkdir(exist_ok=True)
    document = {"fetched_on": clock.today().isoformat(), "queries": QUERIES, "books": rows}
    DATA_FILE.write_text(json.dumps(document, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{len(rows)}권을 저장했습니다: {DATA_FILE}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(run()))
