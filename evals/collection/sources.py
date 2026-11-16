"""실험 장서의 정보나루·카카오 값을 받는다: uv run python -m evals.collection.sources [--dry-run]

YES24 원본 파일(`fetch.py`가 한 번 받아 둔 525권)의 ISBN과 분야를 입력으로, ISBN마다 정보나루
도서 상세와 카카오 책 검색을 한 번씩 불러 새 출처 파일에 남긴다. YES24는 다시 부르지 않는다. 적재
(`scripts/seed_experiment.py`)가 두 파일을 세 출처로 합친다.

출처마다 상태를 둔다: `found`, `not_found`, 아직 받지 않음(`null`). ISBN 하나를 받을 때마다
파일에 쓴다.
- 정보나루가 멈춰야 하는 오류(한도 초과, 인증 실패, 장애)를 내면 그 실행에서는 정보나루를 더 부르지
  않고 카카오는 계속 받는다. 서버 IP를 등록하지 않으면 하루 500건에서 막히기 때문이다(2026-11-16
  사용자 결정). 다시 실행하면 출처마다 받지 않은 ISBN만 부른다.
- 카카오가 그런 오류를 내면 그 자리에서 멈춘다(한도가 넉넉해 실제 장애로 본다).
- 모든 상태가 정해져 있으면 외부를 부르지 않는다(한 번만 받기).

파일은 저장소에 넣지 않는다(`.gitignore`의 `evals/collection/data/`). 카카오 판매가·판매 상태는
넣지 않는다.
종료 코드: 0 완료(정보나루가 남아도 0, 남은 수를 출력), 1 전제 조건, 2 카카오 장애로 중단.
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.central.external.data4library import definitions as d4l_definitions
from app.central.external.data4library.client import Data4LibraryClient, raw_books_by_isbn
from app.central.external.http import SourceStopped
from app.central.external.kakao import definitions as kakao_definitions
from app.central.external.kakao.client import KakaoClient, raw_documents_by_isbn
from app.central.external.kakao.parsing import strip_volatile
from app.central.external.yes24.parsing import parse_item
from app.core import clock
from app.core.config import get_settings
from app.core.isbn import normalize_isbn
from app.seed.experiment import CollectionMissingError, load_collection
from evals.collection.fetch import DATA_FILE as YES24_FILE

SOURCES_FILE = Path(__file__).parent / "data" / "sources_collection.json"
D4L, KAKAO = "data4library", "kakao"
SOURCES = (D4L, KAKAO)
FOUND, NOT_FOUND = "found", "not_found"
PAYLOAD_KEYS = {D4L: "books", KAKAO: "documents"}  # 출처마다 응답 원본을 두는 키

EXIT_OK = 0
EXIT_PRECONDITION = 1
EXIT_STOPPED = 2

Fetcher = Callable[[str], Awaitable[list[dict[str, Any]]]]


@dataclass(frozen=True)
class Target:
    isbn: str
    field: str


def targets(yes24_path: Path = YES24_FILE) -> list[Target]:
    """YES24 원본 파일의 ISBN과 분야. ISBN 순서다(적재와 같은 순서)."""
    collection = load_collection(yes24_path, {})
    rows = {
        normalize_isbn(parse_item(row["item"]).isbn13 or ""): row["field"]
        for row in collection.books
    }
    return [Target(isbn, rows[isbn]) for isbn in sorted(rows)]


def empty_document(books: list[Target]) -> dict[str, Any]:
    return {
        "fetched_on": None,
        "sources": list(SOURCES),
        "books": [
            {"isbn": t.isbn, "field": t.field, **{source: None for source in SOURCES}}
            for t in books
        ],
    }


def load_document(path: Path, books: list[Target]) -> dict[str, Any]:
    """이어 받을 파일. 없으면 빈 문서를 만든다. 입력에 없는 ISBN이 파일에 있으면 오류다."""
    if not path.exists():
        return empty_document(books)
    document = json.loads(path.read_text(encoding="utf-8"))
    known = {row["isbn"] for row in document["books"]}
    wanted = {t.isbn for t in books}
    if known != wanted:
        raise ValueError(f"새 출처 파일의 ISBN이 YES24 원본과 다릅니다: {path}")
    return document


def pending(document: dict[str, Any]) -> dict[str, int]:
    """출처마다 아직 받지 않은 ISBN 수."""
    return {s: sum(1 for row in document["books"] if row[s] is None) for s in SOURCES}


def _write(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(path)  # 쓰는 도중에 멈춰도 앞의 파일이 남는다


def _entry(source: str, payload: list[dict[str, Any]]) -> dict[str, Any]:
    if source == KAKAO:
        payload = [strip_volatile(document) for document in payload]
    return {"status": FOUND if payload else NOT_FOUND, PAYLOAD_KEYS[source]: payload}


@dataclass
class FetchResult:
    called: dict[str, int]
    stopped: dict[str, str]  # 출처 → 중단 사유
    pending: dict[str, int]


async def fetch(
    fetchers: dict[str, Fetcher], books: list[Target], path: Path = SOURCES_FILE
) -> FetchResult:
    """출처마다 받지 않은 ISBN을 부르고 하나 받을 때마다 파일에 쓴다.

    정보나루가 멈추면 정보나루만 멈추고, 카카오가 멈추면 `SourceStopped`를 다시 던진다.
    """
    document = load_document(path, books)
    if document["fetched_on"] is None:
        document["fetched_on"] = clock.today().isoformat()
    called = dict.fromkeys(SOURCES, 0)
    stopped: dict[str, str] = {}
    for row in document["books"]:
        changed = False
        for source in SOURCES:
            if row[source] is not None or source in stopped:
                continue
            try:
                payload = await fetchers[source](row["isbn"])
            except SourceStopped as exc:
                if source == KAKAO:
                    if changed:
                        _write(path, document)
                    raise
                stopped[source] = exc.reason.value
                continue
            called[source] += 1
            row[source] = _entry(source, payload)
            changed = True
        if changed:
            _write(path, document)
    return FetchResult(called, stopped, pending(document))


def dry_run(books: list[Target], path: Path = SOURCES_FILE) -> int:
    left = pending(load_document(path, books))
    print(f"실험 장서 ISBN {len(books)}개. 외부 호출 없음.")
    for source in SOURCES:
        print(f"{source}: 남은 호출 {left[source]}회")
    print(
        f"카카오 일일 한도 30,000의 {left[KAKAO] / 30000:.1%}. 정보나루는 IP 미등록 시 하루 500건."
    )
    return EXIT_OK


def report(result: FetchResult, path: Path) -> None:
    for source in SOURCES:
        line = f"{source}: 호출 {result.called[source]}회, 남은 ISBN {result.pending[source]}개"
        if source in result.stopped:
            line += f" (멈춤: {result.stopped[source]}. 다음에 다시 실행하면 이어 받습니다)"
        print(line)
    print(f"저장했습니다: {path}")


async def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="실험 장서의 정보나루·카카오 값을 받는다")
    parser.add_argument("--dry-run", action="store_true", help="남은 호출 수만 출력")
    args = parser.parse_args(argv)
    try:
        books = targets()
    except CollectionMissingError as exc:
        print(f"{exc}. YES24 원본 파일이 있어야 합니다.", file=sys.stderr)
        return EXIT_PRECONDITION
    if args.dry_run:
        return dry_run(books)
    if not any(pending(load_document(SOURCES_FILE, books)).values()):
        print(f"이미 다 받았습니다: {SOURCES_FILE}. 한 번만 받습니다.", file=sys.stderr)
        return EXIT_PRECONDITION
    settings = get_settings()
    keys = {
        "LIBRARY_BIGDATA_KEY": settings.library_bigdata_key,
        "KAKAO_REST_API_KEY": settings.kakao_rest_api_key,
    }
    values = {name: key.get_secret_value() if key else "" for name, key in keys.items()}
    missing = [name for name, value in values.items() if not value]
    if missing:
        print(f"{', '.join(missing)}가 없습니다.", file=sys.stderr)
        return EXIT_PRECONDITION
    async with (
        httpx.AsyncClient(
            base_url=settings.data4library_base_url,
            timeout=d4l_definitions.REQUEST_TIMEOUT_SECONDS,
        ) as d4l_http,
        httpx.AsyncClient(
            base_url=settings.kakao_base_url, timeout=kakao_definitions.REQUEST_TIMEOUT_SECONDS
        ) as kakao_http,
    ):
        d4l = Data4LibraryClient(d4l_http, values["LIBRARY_BIGDATA_KEY"])
        kakao = KakaoClient(kakao_http, values["KAKAO_REST_API_KEY"])
        fetchers: dict[str, Fetcher] = {
            D4L: lambda isbn: raw_books_by_isbn(d4l, isbn),
            KAKAO: lambda isbn: raw_documents_by_isbn(kakao, isbn),
        }
        try:
            result = await fetch(fetchers, books)
        except SourceStopped as exc:
            print(
                f"중단: {exc.source} {exc.reason.value}. 받은 것은 파일에 남았습니다.",
                file=sys.stderr,
            )
            return EXIT_STOPPED
    report(result, SOURCES_FILE)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(asyncio.run(run(sys.argv[1:])))
