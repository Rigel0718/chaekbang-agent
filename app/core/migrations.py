from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def alembic_config(database_url: str | None = None) -> Config:
    """프로젝트의 alembic.ini를 읽은 Config. URL을 주면 .env 대신 그 DB를 대상으로 한다."""
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    if database_url:
        config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


def head_revision() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()
