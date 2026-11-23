"""[agent/runner] LLM 설정과 모델 가격표, [platform/app-settings] 설정을 읽는 규칙."""

import re
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.central.external.tei import TeiEmbedder
from app.central.models import EMBEDDING_DIM
from app.core.config import ENV_FIELDS, LLM_PRICES, Settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
# `.env.example`에 있되 앱이 읽지 않고 docker-compose.yml만 읽는 키
COMPOSE_ONLY_KEYS = {
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "POSTGRES_DB",
    "POSTGRES_PORT",
    "EMBEDDING_PORT",
}
DATABASE_URL = "postgresql+asyncpg://unused"
POLICY_FIELDS = sorted(set(Settings.model_fields) - ENV_FIELDS)


def _settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    return Settings(_env_file=None, database_url=DATABASE_URL)


def test_settings_load_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """[agent/runner] LLM 설정 / 키 없이 서버 시작"""
    assert _settings(monkeypatch).openai_api_key is None


def test_default_model_has_price(monkeypatch: pytest.MonkeyPatch) -> None:
    """[agent/runner] 모델 가격표 / 기본 모델 가격"""
    price = LLM_PRICES[_settings(monkeypatch).llm_model]
    assert price.input == Decimal("0.10")
    assert price.cached_input == Decimal("0.01")
    assert price.output == Decimal("0.50")
    assert price.checked_on is not None
    assert price.retires_on is None


def test_prices_do_not_use_float() -> None:
    """[agent/runner] 모델 가격표 / 기본 모델 가격"""
    for price in LLM_PRICES.values():
        assert all(isinstance(v, Decimal) for v in (price.input, price.cached_input, price.output))


def _different(default: object) -> object:
    """기본값과 다른 값(타입별)."""
    if isinstance(default, bool):
        return not default
    if isinstance(default, int):
        return default + 1
    if isinstance(default, float):
        return default + 1.0
    return "x"


@pytest.mark.parametrize("name", POLICY_FIELDS)
def test_policy_field_ignores_environment(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """[platform/app-settings] 환경 값과 코드값 분리 / 정책 필드는 환경변수를 무시한다"""
    default = Settings.model_fields[name].default
    monkeypatch.setenv(name.upper(), str(_different(default)))
    settings = Settings(_env_file=None, database_url=DATABASE_URL)
    assert getattr(settings, name) == default


def test_old_keys_in_dotenv_are_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """[platform/app-settings] 환경 값과 코드값 분리 / 옛 키가 든 `.env`"""
    for name in ("LIBRARIAN_MAX_TURNS", "LLM_MODEL", "EMBEDDING_DIM"):
        monkeypatch.delenv(name, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"DATABASE_URL={DATABASE_URL}\nLIBRARIAN_MAX_TURNS=99\nLLM_MODEL=other\nEMBEDDING_DIM=5\n",
        encoding="utf-8",
    )
    settings = Settings(_env_file=env_file)
    assert settings.database_url == DATABASE_URL
    assert settings.librarian_max_turns == Settings.model_fields["librarian_max_turns"].default
    assert settings.llm_model == Settings.model_fields["llm_model"].default
    assert not hasattr(settings, "embedding_dim")


def test_env_fields_read_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """[platform/app-settings] 환경 값과 코드값 분리 / 환경 필드는 환경변수를 읽는다"""
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://from-env")
    monkeypatch.setenv("EMBEDDING_QUERY_ENABLED", "false")
    settings = Settings(_env_file=None)
    assert settings.database_url == "postgresql+asyncpg://from-env"
    assert settings.embedding_query_enabled is False


def test_explicit_values_apply_to_every_field() -> None:
    """[platform/app-settings] 환경 값과 코드값 분리 / 직접 준 값"""
    settings = Settings(_env_file=None, database_url=DATABASE_URL, llm_model="gpt-5-mini")
    assert settings.llm_model == "gpt-5-mini"


def test_encoder_dim_is_schema_constant() -> None:
    """[platform/app-settings] 임베딩 서버와 같은 모델·입력 한도 / 인코더 차원"""
    settings = Settings(_env_file=None, database_url=DATABASE_URL)
    encoder = TeiEmbedder(httpx.AsyncClient(), settings)
    assert encoder.dim == EMBEDDING_DIM


def _embedder_environment() -> dict[str, str]:
    """docker-compose.yml의 embedder `environment` 줄을 이름: 값으로 읽는다."""
    text = (PROJECT_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    block = text[text.index("  embedder:") :]
    block = block[block.index("    environment:") :].split("    ports:")[0]
    pairs = re.findall(r"^      ([A-Z_]+): (.+)$", block, flags=re.MULTILINE)
    return {name: value.strip().strip('"') for name, value in pairs}


def test_compose_embedder_matches_settings() -> None:
    """[platform/app-settings] 임베딩 서버와 같은 모델·입력 한도 / compose와 설정이 같다"""
    env = _embedder_environment()
    assert "${" not in "".join(env.values())
    assert env["EMBEDDING_MODEL"] == Settings.model_fields["embedding_model"].default
    assert env["EMBEDDING_MAX_TOKENS"] == str(Settings.model_fields["embedding_max_tokens"].default)


def test_env_example_keys_match_env_fields() -> None:
    """[platform/app-settings] `.env.example`과 환경 필드의 일치 / 키 집합 비교"""
    text = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    keys = set(re.findall(r"^([A-Z][A-Z0-9_]*)=", text, flags=re.MULTILINE))
    env_keys = {name.upper() for name in ENV_FIELDS}
    assert env_keys <= keys
    assert keys - env_keys <= COMPOSE_ONLY_KEYS
