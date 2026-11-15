"""운영자용 기여자·저자 키 다시 만들기: uv run python scripts/rebuild_contributors.py [--check]

공식 서지의 기여자(`book_contributors`)와 기관 도서의 저자 키(`library_books.author_keys`)를
지금 규칙으로 맞춘다. 마이그레이션 뒤 한 번, 그리고 역할 표나 이름 맞춤 규칙을 고친 뒤 돌린다.
다시 돌려도 결과가 같다. `--check`는 쓰지 않고 지금 규칙과 다른 건수만 출력한다.
맞춰지지 않은 분류기호는 기관 값이라 세기만 한다.
외부 호출이 없다. 종료 코드: 0 완료, 1 전제 조건·인자 문제.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.central.contributors import rebuild_contributors  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.library.services.author_keys import (  # noqa: E402
    count_unnormalized_kdc,
    rebuild_author_keys,
)
from app.seed.runner import (  # noqa: E402
    CONNECT_TIMEOUT_SECONDS,
    SeedPreconditionError,
    check_migrations,
)

EXIT_OK = 0
EXIT_PRECONDITION = 1


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        print(message, file=sys.stderr)
        raise SystemExit(EXIT_PRECONDITION)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = _Parser(description="공식 서지 기여자와 기관 도서 저자 키를 지금 규칙으로 다시 만든다")
    parser.add_argument(
        "--check", action="store_true", help="쓰지 않고 지금 규칙과 다른 건수만 출력"
    )
    return parser.parse_args(argv)


async def execute(session: AsyncSession, *, check: bool) -> int:
    """전제 조건을 확인하고 실행한 뒤 결과를 출력하고 종료 코드를 돌려준다."""
    try:
        await check_migrations(await session.connection())
    except SeedPreconditionError as exc:
        print(str(exc), file=sys.stderr)
        return EXIT_PRECONDITION
    contributors, books = await rebuild_contributors(session, write=not check)
    keys, library_books = await rebuild_author_keys(session, write=not check)
    kdc = await count_unnormalized_kdc(session)
    if not check:  # 확인 방식은 아무것도 쓰지 않았다
        await session.commit()
    verb = "다름" if check else "고침"
    print(f"공식 서지 기여자: {verb} {contributors}건 (공식 서지 {books}건)")
    print(f"기관 도서 저자 키: {verb} {keys}건 (기관 도서 {library_books}건)")
    print(f"맞춰지지 않은 분류기호: {kdc}건 (기관 값이라 고치지 않음)")
    return EXIT_OK


async def run(args: argparse.Namespace) -> int:
    engine = create_async_engine(
        get_settings().database_url,
        poolclass=NullPool,
        connect_args={"timeout": CONNECT_TIMEOUT_SECONDS},
    )
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            return await execute(session, check=args.check)
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
