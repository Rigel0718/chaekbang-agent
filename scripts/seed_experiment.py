"""운영자용 실험 장서 적재: uv run python scripts/seed_experiment.py [--purge] [--sources …]

`evals/collection/fetch.py`가 받아 둔 YES24 파일과 `evals/collection/sources.py`가 받아 둔
정보나루·카카오 파일로 공식 서지(기여자, 시리즈 키, 필드별 출처 포함)를 만들고, `실험용 가상
작은도서관` 하나가 기관 도서와 사본으로 소장하게 한다. 새 출처 파일이 없으면 YES24 값만 쓴다.
개발 DB에서만 돌린다.
다시 돌려도 같은 결과이고, 가상 기관 밖의 기관 데이터는 바꾸지 않는다. 한 트랜잭션으로 넣는다.

- `--purge`: 가상 기관과 그 기관만 참조하던 공식 서지를 지운다(넣지 않는다). 출처를 바꿔 다시
  넣기 전에 쓴다.
- `--sources data4library,kakao`: 합칠 출처를 고른다(기본은 셋 다). 비교 실험용이다.

외부 호출이 없다. 종료 코드: 0 완료, 1 전제 조건(파일 없음, 마이그레이션, 시드 비밀번호, DB 연결,
인자).
"""

import argparse
import asyncio
import sys
from dataclasses import replace
from pathlib import Path

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.seed.experiment import (  # noqa: E402
    LIBRARY_NAME,
    SOURCE_NAMES,
    CollectionMissingError,
    load_collection,
    load_sources,
    purge_experiment,
    seed_experiment,
)
from app.seed.runner import (  # noqa: E402
    CONNECT_TIMEOUT_SECONDS,
    SeedPreconditionError,
    check_migrations,
    seed_passwords,
)
from evals.collection.fetch import DATA_FILE  # noqa: E402
from evals.collection.plan import FIELDS  # noqa: E402
from evals.collection.sources import SOURCES_FILE  # noqa: E402

EXIT_OK = 0
EXIT_PRECONDITION = 1
DB_HINT = "`docker compose up -d db`로 DB를 실행했는지, DATABASE_URL이 맞는지 확인하세요."


def shelves() -> dict[str, str]:
    return {field.key: field.shelf for field in FIELDS}


async def execute(
    session: AsyncSession,
    path: Path = DATA_FILE,
    *,
    sources_path: Path = SOURCES_FILE,
    use: frozenset[str] = frozenset(SOURCE_NAMES),
) -> int:
    """전제 조건을 확인하고 넣은 뒤 건수를 출력한다. 실패하면 아무것도 쓰지 않는다."""
    try:
        collection = load_collection(path, shelves())
    except CollectionMissingError as exc:
        print(f"{exc}. 먼저 `uv run python -m evals.collection.fetch`로 받으세요.", file=sys.stderr)
        return EXIT_PRECONDITION
    sources = load_sources(sources_path)
    collection = replace(collection, sources=sources, use=use)
    try:
        admin_password, kiosk_password = seed_passwords()
        await check_migrations(await session.connection())
    except SeedPreconditionError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_PRECONDITION
    report = await seed_experiment(session, collection, admin_password, kiosk_password)
    await session.commit()
    used = ", ".join(sorted(use)) if sources is not None else "yes24(새 출처 파일 없음)"
    print(f"{LIBRARY_NAME} (받은 날 {collection.fetched_on}, 파일의 책 {len(collection.books)}권)")
    print(f"합친 출처: {used}")
    for table, (created, skipped) in report.items():
        if table == "missing_books":
            print(f"고른 출처 모두 서명·저자가 없어 넣지 않은 책: {created}권")
        else:
            print(f"{table}: 생성 {created}건, 건너뜀 {skipped}건")
    return EXIT_OK


async def purge(session: AsyncSession) -> int:
    try:
        await check_migrations(await session.connection())
    except SeedPreconditionError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_PRECONDITION
    deleted = await purge_experiment(session)
    await session.commit()
    if not deleted:
        print(f"{LIBRARY_NAME}이 없습니다. 지운 것이 없습니다.")
    for table, count in deleted.items():
        print(f"{table}: 지움 {count}건")
    return EXIT_OK


async def run(*, purge_only: bool = False, use: frozenset[str] = frozenset(SOURCE_NAMES)) -> int:
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args={"timeout": CONNECT_TIMEOUT_SECONDS},
    )
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            if purge_only:
                return await purge(session)
            return await execute(session, use=use)
    except (OSError, TimeoutError, DBAPIError) as exc:
        print(f"DB에 연결할 수 없습니다 ({type(exc).__name__}). {DB_HINT}", file=sys.stderr)
        return EXIT_PRECONDITION
    finally:
        await engine.dispose()


def parse_sources(value: str) -> frozenset[str]:
    names = frozenset(name.strip() for name in value.split(",") if name.strip())
    unknown = names - set(SOURCE_NAMES)
    if not names or unknown:
        raise argparse.ArgumentTypeError(
            f"출처는 {', '.join(SOURCE_NAMES)} 중에서 고릅니다: {', '.join(sorted(unknown))}"
        )
    return names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="받아 둔 실험 장서를 개발 DB의 공식 서지와 가상 기관으로 넣는다"
    )
    parser.add_argument("--purge", action="store_true", help="가상 기관과 그 공식 서지를 지운다")
    parser.add_argument(
        "--sources",
        type=parse_sources,
        default=frozenset(SOURCE_NAMES),
        help="합칠 출처(쉼표로). 기본은 data4library,kakao,yes24",
    )
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        return EXIT_PRECONDITION
    return asyncio.run(run(purge_only=args.purge, use=args.sources))


if __name__ == "__main__":
    sys.exit(main())
