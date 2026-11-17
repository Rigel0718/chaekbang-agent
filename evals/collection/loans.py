"""실험 장서의 정보나루 대출 신호를 받는다.

`uv run python -m evals.collection.loans [--dry-run | --overlap]`

대상은 출처 파일(`sources_collection.json`)에서 정보나루 상태가 `found`이고 실험 기관이 공식 서지로
소장한 ISBN이다(ISBN 없이 넣은 책은 부르지 않는다). ISBN마다 도서별 이용 분석(`usageAnalysisList`)을
한 번 부르고, 연령 묶음 넷 × 기간 둘마다 인기대출도서(`loanItemSrch`)를 한 번 부른다.

파일(`loan_signals.json`, 저장소 밖)에는 ISBN 순위와 대출 수, 상태만 둔다. 서명·저자·표지·키워드·
이용자 그룹은 남기지 않는다. 호출 하나를 받을 때마다 파일에 쓴다. 정보나루가 한도 초과·인증 실패·
장애를 돌려주면 그 자리에서 멈추고 남은 호출 수를 출력한다(서버 IP 미등록 시 하루 500건). 다시
실행하면 받지 않은 것만 부른다. 모두 받았으면 부르지 않는다(한 번만 받기).

`--overlap`은 받은 파일과 개발 DB의 실험 기관으로 소장 겹침을 센다(외부 호출 없음).
종료 코드: 0 완료(멈춰서 남아도 0), 1 전제 조건(키 없음, 이미 다 받음, 출처 파일·실험 기관 없음).
"""

import argparse
import asyncio
import json
import sys
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.central.external.data4library import definitions as d4l_definitions
from app.central.external.data4library.client import (
    Data4LibraryClient,
    popular_loans,
    usage_analysis,
)
from app.central.external.data4library.definitions import AGE_GROUPS, AgeGroup
from app.central.external.data4library.parsing import PopularLoans, UsageAnalysis
from app.central.external.http import SourceStopped
from app.central.models import Book
from app.core import clock
from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.library.models.catalog import LibraryBook
from app.library.models.library import Library
from app.seed.experiment import LIBRARY_NAME
from evals.collection.sources import D4L, FOUND, NOT_FOUND, SOURCES_FILE

LOANS_FILE = Path(__file__).parent / "data" / "loan_signals.json"
PERIODS = (90, 365)  # 인기대출도서의 기간(일)
PAGE_SIZE = 1000
USAGE_KEYS = ("co_loans", "mania", "reader")
EXIT_OK = 0
EXIT_PRECONDITION = 1

UsageFetcher = Callable[[str], Awaitable[UsageAnalysis | None]]
PopularFetcher = Callable[[AgeGroup, date, date], Awaitable[PopularLoans]]


@dataclass(frozen=True)
class Condition:
    group: AgeGroup
    days: int

    @property
    def key(self) -> str:
        return f"{self.group.key}-{self.days}"


CONDITIONS = tuple(Condition(group, days) for group in AGE_GROUPS for days in PERIODS)


def condition_key(group: str, days: int) -> str:
    return f"{group}-{days}"


def loan_targets(sources: dict[str, Any], held_isbns: set[str]) -> list[str]:
    """정보나루 상태가 `found`이고 공식 서지로 소장한 ISBN(정렬)."""
    return sorted(
        row["isbn"]
        for row in sources["books"]
        if row["isbn"] in held_isbns and (row.get(D4L) or {}).get("status") == FOUND
    )


def empty_document(isbns: Sequence[str]) -> dict[str, Any]:
    return {
        "fetched_on": None,
        "usage": dict.fromkeys(isbns),
        "popular": {condition.key: None for condition in CONDITIONS},
    }


def load_document(path: Path, isbns: Sequence[str]) -> dict[str, Any]:
    """이어 받을 파일. 없으면 빈 문서다. 대상과 파일의 ISBN이 다르면 오류다."""
    if not path.exists():
        return empty_document(isbns)
    document = json.loads(path.read_text(encoding="utf-8"))
    if set(document["usage"]) != set(isbns):
        raise ValueError(f"대출 신호 파일의 ISBN이 대상과 다릅니다: {path}")
    return document


def pending(document: dict[str, Any]) -> dict[str, int]:
    """API마다 아직 받지 않은 호출 수."""
    return {
        "usageAnalysisList": sum(1 for v in document["usage"].values() if v is None),
        "loanItemSrch": sum(1 for v in document["popular"].values() if v is None),
    }


def _write(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=1), encoding="utf-8")
    temporary.replace(path)


def usage_entry(result: UsageAnalysis | None) -> dict[str, Any]:
    if result is None:
        return {"status": NOT_FOUND}
    return {
        "status": FOUND,
        "co_loans": list(result.co_loans),
        "mania": list(result.mania),
        "reader": list(result.reader),
        "loan_count": result.loan_count,
    }


@dataclass
class FetchResult:
    called: dict[str, int]
    stopped: str | None  # 중단 사유
    pending: dict[str, int]


async def fetch(
    usage: UsageFetcher,
    popular: PopularFetcher,
    isbns: Sequence[str],
    path: Path = LOANS_FILE,
    today: date | None = None,
) -> FetchResult:
    """받지 않은 이용 분석, 그다음 인기 조건을 부르고 하나 받을 때마다 파일에 쓴다."""
    document = load_document(path, isbns)
    today = today or clock.today()
    if document["fetched_on"] is None:
        document["fetched_on"] = today.isoformat()
    called = {"usageAnalysisList": 0, "loanItemSrch": 0}
    try:
        for isbn in sorted(document["usage"]):
            if document["usage"][isbn] is not None:
                continue
            document["usage"][isbn] = usage_entry(await usage(isbn))
            called["usageAnalysisList"] += 1
            _write(path, document)
        end = today - timedelta(days=1)
        for condition in CONDITIONS:
            if document["popular"][condition.key] is not None:
                continue
            start = today - timedelta(days=condition.days)
            result = await popular(condition.group, start, end)
            document["popular"][condition.key] = {
                "start": start.isoformat(),
                "end": end.isoformat(),
                "isbns": list(result.isbns),
                "loan_counts": list(result.loan_counts),
            }
            called["loanItemSrch"] += 1
            _write(path, document)
    except SourceStopped as exc:
        return FetchResult(called, exc.reason.value, pending(document))
    return FetchResult(called, None, pending(document))


def dry_run(isbns: Sequence[str], path: Path = LOANS_FILE) -> int:
    left = pending(load_document(path, isbns))
    print(f"대상 ISBN {len(isbns)}개. 외부 호출 없음.")
    for api, count in left.items():
        print(f"{api}: 남은 호출 {count}회")
    total = sum(left.values())
    print(f"합계 {total}회. 정보나루는 서버 IP 미등록 시 하루 500건({total / 500:.1%}).")
    return EXIT_OK


def report(result: FetchResult, path: Path) -> None:
    for api, count in result.called.items():
        print(f"{api}: 호출 {count}회, 남은 호출 {result.pending[api]}회")
    if result.stopped:
        print(f"멈춤: {result.stopped}. 다음에 다시 실행하면 이어 받습니다.")
    print(f"저장했습니다: {path}")


# --- 소장 겹침 ---


@dataclass(frozen=True)
class Holding:
    library_book_id: int
    children: bool
    recommendable: bool


def overlap_lines(document: dict[str, Any], held: dict[str, Holding]) -> list[str]:
    """함께 대출·마니아·다독자의 소장 겹침 분포와 인기 조건마다의 길이·가진 책."""
    lines: list[str] = []
    found = {isbn: entry for isbn, entry in document["usage"].items() if entry}
    taken = [entry for entry in found.values() if entry["status"] == FOUND]
    lines.append(
        f"이용 분석: 받음 {len(found)}/{len(document['usage'])}, 찾음 {len(taken)}, "
        f"찾지 못함 {len(found) - len(taken)}"
    )
    for key in USAGE_KEYS:
        counts = [sum(1 for isbn in entry[key] if isbn in held) for entry in taken]
        lengths = [len(entry[key]) for entry in taken]
        zero = sum(1 for c in counts if c == 0)
        few = sum(1 for c in counts if 1 <= c <= 2)
        many = sum(1 for c in counts if c >= 3)
        mean = sum(counts) / len(counts) if counts else 0.0
        lines.append(
            f"{key}: 순위 길이 합 {sum(lengths)}, 가진 책 합 {sum(counts)}, "
            f"기준 책별 0권 {zero} / 1~2권 {few} / 3권 이상 {many}, 평균 {mean:.2f}"
        )
    for key, entry in document["popular"].items():
        if entry is None:
            lines.append(f"인기 {key}: 받지 않음")
            continue
        books = [held[isbn] for isbn in entry["isbns"] if isbn in held]
        lines.append(
            f"인기 {key}({entry['start']}~{entry['end']}): 길이 {len(entry['isbns'])}, "
            f"가진 책 {len(books)}, 어린이 도서 {sum(1 for b in books if b.children)}, "
            f"추천 가능 {sum(1 for b in books if b.recommendable)}"
        )
    return lines


def seed_lines(document: dict[str, Any], held: dict[str, Holding], seeds: list[str]) -> list[str]:
    """기준 책(ISBN 키) 중 함께 대출 등이 비지 않은 수."""
    lines = []
    for key in USAGE_KEYS:
        filled = 0
        for isbn in seeds:
            entry = document["usage"].get(isbn) or {}
            others = [i for i in entry.get(key, ()) if i in held and i != isbn]
            filled += bool(others)
        lines.append(f"기준 책 {len(seeds)}권 중 {key} 비지 않음: {filled}")
    return lines


async def experiment_library_id(session: AsyncSession) -> int | None:
    return await session.scalar(select(Library.id).where(Library.name == LIBRARY_NAME))


async def held_official_isbns(session: AsyncSession, library_id: int) -> set[str]:
    rows = await session.scalars(
        select(Book.isbn)
        .join(LibraryBook, LibraryBook.book_id == Book.id)
        .where(LibraryBook.library_id == library_id)
    )
    return set(rows)


async def holdings(session: AsyncSession, library_id: int) -> dict[str, Holding]:
    """실험 기관의 ISBN(공식 서지 먼저) → 기관 도서, 어린이 도서 여부, 추천 가능 여부."""
    from app.features.children.service import children_book_ids
    from app.library.recommendation.search import recommendable_ids

    children = set(await session.scalars(children_book_ids(library_id)))
    recommendable = set(await session.scalars(recommendable_ids(library_id)))
    rows = await session.execute(
        select(LibraryBook.id, Book.isbn, LibraryBook.isbn)
        .outerjoin(Book, Book.id == LibraryBook.book_id)
        .where(LibraryBook.library_id == library_id)
    )
    held: dict[str, Holding] = {}
    for book_id, official, own in rows:
        isbn = official or own
        if isbn:
            held[isbn] = Holding(book_id, book_id in children, book_id in recommendable)
    return held


def _seed_isbns() -> list[str]:
    from evals.recommendation.keys import DATA_DIR

    lines: list[str] = []
    for name in ("seeds.json", "seeds-holdout.json"):
        path = DATA_DIR / name
        if path.exists():
            seeds = json.loads(path.read_text(encoding="utf-8")).get("similar", [])
            lines += [
                s["book"].removeprefix("isbn:") for s in seeds if s["book"].startswith("isbn:")
            ]
    return lines


async def run(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="실험 장서의 정보나루 대출 신호를 받는다")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="남은 호출 수만 출력")
    mode.add_argument("--overlap", action="store_true", help="받은 파일의 소장 겹침을 센다")
    args = parser.parse_args(argv)
    if not SOURCES_FILE.exists():
        print(f"출처 파일이 없습니다: {SOURCES_FILE}", file=sys.stderr)
        return EXIT_PRECONDITION
    sources = json.loads(SOURCES_FILE.read_text(encoding="utf-8"))
    async with get_sessionmaker()() as session:
        library_id = await experiment_library_id(session)
        if library_id is None:
            print(
                "실험 기관이 없습니다. uv run python scripts/seed_experiment.py",
                file=sys.stderr,
            )
            return EXIT_PRECONDITION
        isbns = loan_targets(sources, await held_official_isbns(session, library_id))
        if args.overlap:
            if not LOANS_FILE.exists():
                print(f"대출 신호 파일이 없습니다: {LOANS_FILE}", file=sys.stderr)
                return EXIT_PRECONDITION
            document = load_document(LOANS_FILE, isbns)
            held = await holdings(session, library_id)
            for line in [
                *overlap_lines(document, held),
                *seed_lines(document, held, _seed_isbns()),
            ]:
                print(line)
            return EXIT_OK
    if args.dry_run:
        return dry_run(isbns)
    if not any(pending(load_document(LOANS_FILE, isbns)).values()):
        print(f"이미 다 받았습니다: {LOANS_FILE}. 한 번만 받습니다.", file=sys.stderr)
        return EXIT_PRECONDITION
    settings = get_settings()
    key = settings.library_bigdata_key.get_secret_value() if settings.library_bigdata_key else ""
    if not key:
        print("LIBRARY_BIGDATA_KEY가 없습니다.", file=sys.stderr)
        return EXIT_PRECONDITION
    async with httpx.AsyncClient(
        base_url=settings.data4library_base_url, timeout=d4l_definitions.REQUEST_TIMEOUT_SECONDS
    ) as http:
        client = Data4LibraryClient(http, key)
        result = await fetch(
            lambda isbn: usage_analysis(client, isbn),
            lambda group, start, end: popular_loans(client, group, start, end, PAGE_SIZE),
            isbns,
        )
    report(result, LOANS_FILE)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(asyncio.run(run(sys.argv[1:])))
