"""운영자용 실험 장서 적재: uv run python scripts/seed_experiment.py

`evals/collection/fetch.py`가 받아 둔 YES24 파일로 공식 서지(기여자, 시리즈 키 포함)를 만들고,
`실험용 가상 작은도서관` 하나가 기관 도서와 사본으로 소장하게 한다. 개발 DB에서만 돌린다.
다시 돌려도 같은 결과이고, 가상 기관 밖의 기관 데이터는 바꾸지 않는다. 한 트랜잭션으로 넣는다.
외부 호출이 없다. 종료 코드: 0 완료, 1 전제 조건(파일 없음, 마이그레이션, 시드 비밀번호, DB 연결).
"""

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.seed.experiment import (  # noqa: E402
    LIBRARY_NAME,
    CollectionMissingError,
    load_collection,
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

EXIT_OK = 0
EXIT_PRECONDITION = 1
DB_HINT = "`docker compose up -d db`로 DB를 실행했는지, DATABASE_URL이 맞는지 확인하세요."


def shelves() -> dict[str, str]:
    return {field.key: field.shelf for field in FIELDS}


async def execute(session: AsyncSession, path: Path = DATA_FILE) -> int:
    """전제 조건을 확인하고 넣은 뒤 건수를 출력한다. 실패하면 아무것도 쓰지 않는다."""
    try:
        collection = load_collection(path, shelves())
    except CollectionMissingError as exc:
        print(f"{exc}. 먼저 `uv run python -m evals.collection.fetch`로 받으세요.", file=sys.stderr)
        return EXIT_PRECONDITION
    try:
        admin_password, kiosk_password = seed_passwords()
        await check_migrations(await session.connection())
    except SeedPreconditionError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_PRECONDITION
    report = await seed_experiment(session, collection, admin_password, kiosk_password)
    await session.commit()
    print(f"{LIBRARY_NAME} (받은 날 {collection.fetched_on}, 파일의 책 {len(collection.books)}권)")
    for table, (created, skipped) in report.items():
        print(f"{table}: 생성 {created}건, 건너뜀 {skipped}건")
    return EXIT_OK


async def run() -> int:
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
        connect_args={"timeout": CONNECT_TIMEOUT_SECONDS},
    )
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            return await execute(session)
    except (OSError, TimeoutError, DBAPIError) as exc:
        print(f"DB에 연결할 수 없습니다 ({type(exc).__name__}). {DB_HINT}", file=sys.stderr)
        return EXIT_PRECONDITION
    finally:
        await engine.dispose()


def main(argv: list[str] | None = None) -> int:
    argparse.ArgumentParser(
        description="받아 둔 YES24 실험 장서를 개발 DB의 공식 서지와 가상 기관으로 넣는다"
    ).parse_args(argv)
    return asyncio.run(run())


if __name__ == "__main__":
    sys.exit(main())
