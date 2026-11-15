"""임베딩 확인용: 질의와 코사인 유사도가 높은 책 5권을 한 기관 안에서 찾아 출력한다.

  uv run python scripts/embedding_search.py "공룡을 좋아하는 아이" --library-id 1
  uv run python scripts/embedding_search.py "공룡을 좋아하는 아이" --sample

--library-id는 개발 DB에서 찾는다. 먼저 scripts/embed_books.py로 적재해야 한다.
--sample은 평가 표본(evals/librarian/data/)을 테스트 DB의 트랜잭션 안에서 가상 기관에 넣고,
전체 적재 → 증분 적재(0건이어야 한다) → 조회를 한 뒤 모두 되돌린다. 표본은 개발 DB에 넣지 않는다.
종료 코드: 0 완료, 1 전제 조건·인자 문제, 2 임베딩 서버 장애로 중단(또는 증분 재실행이 0건이 아님).
"""

import argparse
import asyncio
import sys
import time
from pathlib import Path

import httpx
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.central.embedding import Embedder, EmbeddingError  # noqa: E402
from app.central.external.tei import TeiEmbedder  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.library.models.library import Library  # noqa: E402
from app.library.recommendation.embeddings import similar_books  # noqa: E402
from app.seed.runner import (  # noqa: E402
    CONNECT_TIMEOUT_SECONDS,
    SeedPreconditionError,
    check_migrations,
)
from evals.librarian.catalog import (  # noqa: E402
    DATA_FILE,
    Sample,
    SampleMissingError,
    load_catalog,
    load_sample,
)
from scripts.embed_books import (  # noqa: E402
    DB_HINT,
    EXIT_OK,
    EXIT_PRECONDITION,
    EXIT_STOPPED,
    Parser,
    describe,
    load_layers,
    report_failure,
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = Parser(description="질의와 임베딩이 가까운 책 5권을 한 기관 안에서 찾는다")
    parser.add_argument("query", help="찾을 문장")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--library-id", type=int, help="개발 DB의 이 기관에서 찾는다")
    scope.add_argument(
        "--sample",
        action="store_true",
        help="평가 표본을 테스트 DB에 넣어 적재하고 찾은 뒤 되돌린다",
    )
    args = parser.parse_args(argv)
    if not args.query.strip():
        parser.error("질의가 비어 있습니다")
    return args


async def search(session: AsyncSession, embedder: Embedder, library_id: int, query: str) -> int:
    """상위 5권을 출력한다. 그 기관의 추천 가능한 책만 나온다."""
    try:
        found = await similar_books(session, embedder, library_id=library_id, query=query)
    except EmbeddingError as exc:
        return report_failure(exc)
    print(f"질의: {query} (기관 {library_id}, 모델 {embedder.name})")
    if not found:
        print("결과가 없습니다. 먼저 scripts/embed_books.py로 이 기관의 도서를 적재하세요.")
        return EXIT_OK
    for rank, item in enumerate(found, start=1):
        book = item.library_book
        print(f"{rank}. {item.similarity:.3f}  {book.shown('title')} / {book.shown('author')}")
    return EXIT_OK


async def execute(session: AsyncSession, embedder: Embedder, library_id: int, query: str) -> int:
    if await session.get(Library, library_id) is None:
        print(f"기관 {library_id}이(가) 없습니다.", file=sys.stderr)
        return EXIT_PRECONDITION
    try:
        await embedder.check()
    except EmbeddingError as exc:
        return report_failure(exc)
    return await search(session, embedder, library_id, query)


async def execute_sample(
    session: AsyncSession, embedder: Embedder, sample: Sample, query: str, *, batch_size: int
) -> int:
    """표본을 가상 기관에 넣고 두 층 전체 적재 → 증분 적재 → 조회를 한다.

    되돌리기는 부르는 쪽이 한다.
    표본 중 공식 서지가 있는 책은 공식 서지 벡터, ISBN 없이 넣은 책은 기관 도서 벡터가 된다.
    """
    try:
        await embedder.check()
    except EmbeddingError as exc:
        return report_failure(exc)
    catalog = await load_catalog(session, sample)
    await session.commit()
    print(f"표본 {len(sample.books)}권을 가상 기관 {catalog.library_id}에 넣었습니다.")

    started = time.monotonic()
    full = await load_layers(
        session, embedder, full=True, library_id=catalog.library_id, batch_size=batch_size
    )
    print(
        "전체 적재: "
        + " / ".join(describe(name, run) for name, run in full)
        + f" ({time.monotonic() - started:.1f}초)"
    )
    for _, run in full:
        if run.stopped is not None:
            return report_failure(run.stopped)

    again = await load_layers(
        session,
        embedder,
        full=False,
        library_id=catalog.library_id,
        batch_size=batch_size,
        progress=False,
    )
    print("증분 적재: " + " / ".join(describe(name, run) for name, run in again))
    for _, run in again:
        if run.stopped is not None:
            return report_failure(run.stopped)
    if any(run.encoded != 0 for _, run in again):
        print("증분 재실행의 인코딩이 0건이 아닙니다.", file=sys.stderr)
        return EXIT_STOPPED
    return await search(session, embedder, catalog.library_id, query)


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    sample = None
    database_url = settings.database_url
    if args.sample:
        if not settings.test_database_url:
            print("TEST_DATABASE_URL이 없습니다. .env.example을 참고하세요.", file=sys.stderr)
            return EXIT_PRECONDITION
        database_url = settings.test_database_url
        try:
            sample = load_sample(DATA_FILE)
        except SampleMissingError as exc:
            print(f"{exc}. 표본은 저장소에 없습니다(YES24 이용 조건).", file=sys.stderr)
            return EXIT_PRECONDITION

    engine = create_async_engine(
        database_url, poolclass=NullPool, connect_args={"timeout": CONNECT_TIMEOUT_SECONDS}
    )
    try:
        async with (
            engine.connect() as conn,
            httpx.AsyncClient(
                base_url=settings.embedding_base_url, timeout=settings.embedding_timeout_seconds
            ) as http,
        ):
            outer = await conn.begin()
            await check_migrations(conn)
            # 적재 코드의 commit은 savepoint로 처리되고, 끝나면 바깥 트랜잭션을 되돌린다.
            session = AsyncSession(
                bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
            )
            embedder = TeiEmbedder(http, settings)
            try:
                if sample is not None:
                    return await execute_sample(
                        session,
                        embedder,
                        sample,
                        args.query,
                        batch_size=settings.embedding_batch_size,
                    )
                return await execute(session, embedder, args.library_id, args.query)
            finally:
                await session.close()
                await outer.rollback()
    except SeedPreconditionError as exc:
        hint = " 테스트 DB는 `uv run pytest`를 한 번 돌리면 최신이 됩니다." if args.sample else ""
        print(f"{exc}{hint}", file=sys.stderr)
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
