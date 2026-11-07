"""운영자용 서지정보 채움: uv run python scripts/enrich_books.py --limit 100

소장 도서의 ISBN으로 YES24를 조회해 공식 서지를 만든다.
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

from app.core.config import get_settings  # noqa: E402
from app.external.yes24.client import Yes24Client  # noqa: E402
from app.external.yes24.definitions import REQUEST_TIMEOUT_SECONDS  # noqa: E402
from app.seed.runner import (  # noqa: E402
    CONNECT_TIMEOUT_SECONDS,
    SeedPreconditionError,
    check_migrations,
)
from app.services.book_enrichment import DEFAULT_LIMIT, run_enrichment  # noqa: E402

EXIT_OK = 0
EXIT_PRECONDITION = 1
EXIT_STOPPED = 2


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        print(message, file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = _Parser(description="소장 도서의 공식 서지를 YES24로 채운다")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="처리할 ISBN 수")
    parser.add_argument(
        "--retry-failed", action="store_true", help="찾지 못한 도서를 처리 대기 뒤에 다시 조회"
    )
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit은 1 이상이어야 합니다")
    return args


async def execute(
    session: AsyncSession, client: Yes24Client, *, limit: int, retry_failed: bool
) -> int:
    """채움을 실행하고 결과를 출력한 뒤 종료 코드를 돌려준다."""
    result = await run_enrichment(session, client, limit=limit, retry_failed=retry_failed)
    print(
        f"처리 {result.processed}건 (새 공식 서지 {result.enriched}, 연결 {result.linked}, "
        f"못 찾음 {result.not_found}, ISBN 불일치 {result.mismatch}), "
        f"남은 처리 대기 {result.remaining}건"
    )
    if result.stopped is not None:
        print(f"중단: {result.stopped.value}", file=sys.stderr)
        return EXIT_STOPPED
    return EXIT_OK


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    key = settings.yes24_api_key.get_secret_value() if settings.yes24_api_key else ""
    if not key:
        print("YES24_API_KEY가 없습니다. .env에 설정하세요 (.env.example 참고).", file=sys.stderr)
        return EXIT_PRECONDITION

    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args={"timeout": CONNECT_TIMEOUT_SECONDS},
    )
    try:
        async with (
            AsyncSession(engine, expire_on_commit=False) as session,
            httpx.AsyncClient(
                base_url=settings.yes24_base_url, timeout=REQUEST_TIMEOUT_SECONDS
            ) as http,
        ):
            await check_migrations(await session.connection())
            await session.commit()
            return await execute(
                session, Yes24Client(http, key), limit=args.limit, retry_failed=args.retry_failed
            )
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
