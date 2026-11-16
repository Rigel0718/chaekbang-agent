"""운영자용 서지정보 채움: uv run python scripts/enrich_books.py --limit 100

소장 도서의 ISBN으로 도서관 정보나루, 카카오 책 검색, YES24를 조회해 공식 서지를 만든다.
세 키(LIBRARY_BIGDATA_KEY, KAKAO_REST_API_KEY, YES24_API_KEY)가 모두 있어야 한다.
종료 코드: 0 완료, 1 전제 조건·인자·키 문제, 2 외부 장애로 중단.
"""

import argparse
import asyncio
import sys
from pathlib import Path

import httpx
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.central.enrichment import (  # noqa: E402
    DEFAULT_LIMIT,
    Lookup,
    lookup_sources,
    run_enrichment,
)
from app.central.external.data4library import definitions as data4library  # noqa: E402
from app.central.external.data4library.client import Data4LibraryClient  # noqa: E402
from app.central.external.kakao import definitions as kakao  # noqa: E402
from app.central.external.kakao.client import KakaoClient  # noqa: E402
from app.central.external.yes24 import definitions as yes24  # noqa: E402
from app.central.external.yes24.client import Yes24Client  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.library.enrichment_targets import LibraryEnrichmentTargets  # noqa: E402
from app.seed.runner import (  # noqa: E402
    CONNECT_TIMEOUT_SECONDS,
    SeedPreconditionError,
    check_migrations,
)

EXIT_OK = 0
EXIT_PRECONDITION = 1
EXIT_STOPPED = 2


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        print(message, file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = _Parser(description="소장 도서의 공식 서지를 정보나루·카카오·YES24로 채운다")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="처리할 ISBN 수")
    parser.add_argument(
        "--retry-failed", action="store_true", help="찾지 못한 도서를 처리 대기 뒤에 다시 조회"
    )
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit은 1 이상이어야 합니다")
    return args


async def execute(session: AsyncSession, lookup: Lookup, *, limit: int, retry_failed: bool) -> int:
    """채움을 실행하고 결과를 출력한 뒤 종료 코드를 돌려준다."""
    targets = LibraryEnrichmentTargets(session)
    result = await run_enrichment(session, lookup, targets, limit=limit, retry_failed=retry_failed)
    print(
        f"처리 {result.processed}건 (새 공식 서지 {result.enriched}, 연결 {result.linked}, "
        f"못 찾음 {result.not_found}, ISBN 불일치 {result.mismatch}), "
        f"남은 처리 대기 {result.remaining}건"
    )
    if result.stopped is not None:
        print(f"중단: {result.stopped_source} {result.stopped.value}", file=sys.stderr)
        return EXIT_STOPPED
    return EXIT_OK


KEY_NAMES = ("LIBRARY_BIGDATA_KEY", "KAKAO_REST_API_KEY", "YES24_API_KEY")


def source_keys(settings) -> tuple[str, str, str] | None:  # noqa: ANN001
    """(정보나루 키, 카카오 키, YES24 키). 하나라도 없으면 빠진 키 이름을 알리고 None이다."""
    keys = (settings.library_bigdata_key, settings.kakao_rest_api_key, settings.yes24_api_key)
    values = [key.get_secret_value() if key else "" for key in keys]
    missing = [name for name, value in zip(KEY_NAMES, values, strict=True) if not value]
    if missing:
        print(
            f"{', '.join(missing)}가 없습니다. .env에 설정하세요 (.env.example 참고).",
            file=sys.stderr,
        )
        return None
    return values[0], values[1], values[2]


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    keys = source_keys(settings)
    if keys is None:
        return EXIT_PRECONDITION
    data4library_key, kakao_key, yes24_key = keys

    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args={"timeout": CONNECT_TIMEOUT_SECONDS},
    )
    try:
        async with (
            AsyncSession(engine, expire_on_commit=False) as session,
            httpx.AsyncClient(
                base_url=settings.data4library_base_url,
                timeout=data4library.REQUEST_TIMEOUT_SECONDS,
            ) as data4library_http,
            httpx.AsyncClient(
                base_url=settings.kakao_base_url, timeout=kakao.REQUEST_TIMEOUT_SECONDS
            ) as kakao_http,
            httpx.AsyncClient(
                base_url=settings.yes24_base_url, timeout=yes24.REQUEST_TIMEOUT_SECONDS
            ) as yes24_http,
        ):
            await check_migrations(await session.connection())
            await session.commit()
            lookup = lookup_sources(
                Data4LibraryClient(data4library_http, data4library_key),
                KakaoClient(kakao_http, kakao_key),
                Yes24Client(yes24_http, yes24_key),
            )
            return await execute(session, lookup, limit=args.limit, retry_failed=args.retry_failed)
    except SeedPreconditionError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_PRECONDITION
    except (OSError, TimeoutError, DBAPIError) as exc:
        print(
            f"DB에 연결할 수 없습니다 ({type(exc).__name__}). "
            "`docker compose up -d db`로 DB를 실행했는지, DATABASE_URL이 맞는지 확인하세요.",
            file=sys.stderr,
        )
        return EXIT_PRECONDITION
    finally:
        await engine.dispose()


def main() -> int:
    return asyncio.run(run(parse_args(sys.argv[1:])))


if __name__ == "__main__":
    sys.exit(main())
