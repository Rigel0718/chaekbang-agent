"""운영자용 도서 임베딩 적재: uv run python scripts/embed_books.py --incremental

추천 가능한 기관 도서의 임베딩 텍스트를 로컬 임베딩 서버로 인코딩해 `book_embeddings`에 저장한다.
--full은 모두 다시 인코딩하고, --incremental은 벡터가 없거나 텍스트가 바뀐 책만 인코딩한다.
임베딩 서버: docker compose --profile embedding up -d embedder
종료 코드: 0 완료, 1 전제 조건·인자 문제(서버의 모델·한도 불일치 포함), 2 임베딩 서버 장애로 중단.
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

from app.central.embedding import Embedder, EmbeddingError, EmbeddingFailure  # noqa: E402
from app.central.external.tei import TeiEmbedder  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.library.models.library import Library  # noqa: E402
from app.library.recommendation.embedding_text import TEXT_VERSION  # noqa: E402
from app.library.recommendation.embeddings import EmbeddingRun, run_embedding  # noqa: E402
from app.seed.runner import (  # noqa: E402
    CONNECT_TIMEOUT_SECONDS,
    SeedPreconditionError,
    check_migrations,
)

EXIT_OK = 0
EXIT_PRECONDITION = 1
EXIT_STOPPED = 2

START_HINT = "`docker compose --profile embedding up -d embedder`"
DB_HINT = "`docker compose up -d db`로 DB를 실행했는지, DATABASE_URL이 맞는지 확인하세요."


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        print(message, file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = Parser(description="추천 가능한 기관 도서의 임베딩 벡터를 만든다")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--full", action="store_true", help="대상 도서를 모두 다시 인코딩")
    mode.add_argument(
        "--incremental", action="store_true", help="벡터가 없거나 텍스트가 바뀐 도서만 인코딩"
    )
    parser.add_argument("--library-id", type=int, help="이 기관만 (없으면 모든 기관)")
    parser.add_argument("--batch-size", type=int, help="한 번에 인코딩할 권수 (기본: 설정 값)")
    args = parser.parse_args(argv)
    if args.batch_size is not None and args.batch_size < 1:
        parser.error("--batch-size는 1 이상이어야 합니다")
    return args


def report_failure(error: EmbeddingError) -> int:
    """멈춘 이유를 출력하고 종료 코드를 돌려준다."""
    if error.failure is EmbeddingFailure.MODEL_MISMATCH:
        print(
            f"임베딩 서버가 설정과 다릅니다 ({error.detail}). "
            ".env의 EMBEDDING_MODEL·EMBEDDING_MAX_TOKENS와 맞춰 서버를 다시 띄우세요.",
            file=sys.stderr,
        )
        return EXIT_PRECONDITION
    if error.failure is EmbeddingFailure.UNREACHABLE:
        print(
            f"중단: 임베딩 서버에 연결할 수 없습니다 ({get_settings().embedding_base_url}). "
            f"{START_HINT}로 켜세요. 처음에는 모델을 내려받는 동안 기다려야 합니다.",
            file=sys.stderr,
        )
    else:
        print(f"중단: 임베딩 서버 오류 ({error})", file=sys.stderr)
    return EXIT_STOPPED


def print_progress(run: EmbeddingRun) -> None:
    print(f"[{run.done}/{run.targets}] 인코딩 {run.encoded}, 건너뜀 {run.skipped}", flush=True)


async def execute(
    session: AsyncSession,
    embedder: Embedder,
    *,
    full: bool,
    library_id: int | None,
    batch_size: int,
) -> int:
    """적재를 실행하고 결과를 출력한 뒤 종료 코드를 돌려준다."""
    if library_id is not None and await session.get(Library, library_id) is None:
        print(f"기관 {library_id}이(가) 없습니다.", file=sys.stderr)
        return EXIT_PRECONDITION
    await session.commit()
    try:
        await embedder.check()
    except EmbeddingError as exc:
        return report_failure(exc)
    run = await run_embedding(
        session,
        embedder,
        full=full,
        library_id=library_id,
        batch_size=batch_size,
        on_progress=print_progress,
    )
    print(
        f"대상 {run.targets}권: 인코딩 {run.encoded}건, 건너뜀 {run.skipped}건 "
        f"(모델 {embedder.name}, 텍스트 버전 {TEXT_VERSION})"
    )
    if run.stopped is not None:
        return report_failure(run.stopped)
    return EXIT_OK


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args={"timeout": CONNECT_TIMEOUT_SECONDS},
    )
    try:
        async with (
            AsyncSession(engine, expire_on_commit=False) as session,
            httpx.AsyncClient(
                base_url=settings.embedding_base_url, timeout=settings.embedding_timeout_seconds
            ) as http,
        ):
            await check_migrations(await session.connection())
            await session.commit()
            return await execute(
                session,
                TeiEmbedder(http, settings),
                full=args.full,
                library_id=args.library_id,
                batch_size=args.batch_size or settings.embedding_batch_size,
            )
    except SeedPreconditionError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_PRECONDITION
    except (OSError, TimeoutError, DBAPIError) as exc:
        print(f"DB에 연결할 수 없습니다 ({type(exc).__name__}). {DB_HINT}", file=sys.stderr)
        return EXIT_PRECONDITION
    finally:
        await engine.dispose()


def main() -> int:
    return asyncio.run(run(parse_args(sys.argv[1:])))


if __name__ == "__main__":
    sys.exit(main())
