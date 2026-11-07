"""[agent/runner] LLM 설정과 모델 가격표."""

from decimal import Decimal

import pytest

from app.core.config import LLM_PRICES, Settings


def _settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for name in ("OPENAI_API_KEY", "LLM_MODEL"):
        monkeypatch.delenv(name, raising=False)
    return Settings(_env_file=None, database_url="postgresql+asyncpg://unused")


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
