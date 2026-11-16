from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, text

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def alembic_config(database_url: str | None = None) -> Config:
    """프로젝트의 alembic.ini를 읽은 Config. URL을 주면 .env 대신 그 DB를 대상으로 한다."""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def head_revision() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def require_collation(connection: Connection, name: str) -> None:
    """collation이 데이터베이스에 없으면 이름을 담은 오류로 멈춘다. 마이그레이션이 부른다."""
    found = connection.scalar(
        text("SELECT 1 FROM pg_collation WHERE collname = :name"), {"name": name}
    )
    if found is None:
        raise RuntimeError(
            f"PostgreSQL에 '{name}' collation이 없습니다. "
            "서명 정렬에 쓰므로 ICU로 빌드된 PostgreSQL(지금 이미지 pgvector/pgvector)이 "
            "필요합니다."
        )
