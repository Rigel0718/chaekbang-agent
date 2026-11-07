from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class ModelPrice:
    """표준 등급의 1M 토큰당 가격(USD). 긴 입력 할증과 Batch 가격은 넣지 않는다."""

    input: Decimal
    cached_input: Decimal
    output: Decimal
    checked_on: date  # 공식 가격표에서 확인한 날
    retires_on: date | None = None  # API에서 제거될 예정일


# 모델별 토큰 가격. 비용을 비교할 때 참고한다. 출처: developers.openai.com/api/docs/pricing
# 캐시 쓰기는 입력 가격의 1.25배가 따로 붙는다 (30분 보관 기준).
LLM_PRICES: dict[str, ModelPrice] = {
    # 기본 모델
    "gpt-6-luna": ModelPrice(
        input=Decimal("0.10"),
        cached_input=Decimal("0.01"),
        output=Decimal("0.50"),
        checked_on=date(2026, 11, 7),
    ),
    # 비교용. 2026-12-11에 제거되며 공식 대체 모델은 gpt-5.6-terra다
    "gpt-5-mini": ModelPrice(
        input=Decimal("0.25"),
        cached_input=Decimal("0.025"),
        output=Decimal("2.00"),
        checked_on=date(2026, 11, 7),
        retires_on=date(2026, 12, 11),
    ),
    # 비교용
    "gpt-5.6-terra": ModelPrice(
        input=Decimal("2.00"),
        cached_input=Decimal("0.20"),
        output=Decimal("12.00"),
        checked_on=date(2026, 11, 7),
    ),
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    test_database_url: str | None = None

    # 인증 토큰 만료 시간. 키오스크는 도서관 PC에 켜 두는 화면이라 길다.
    admin_token_hours: int = 12
    kiosk_token_hours: int = 720

    # "오늘"(대출일, 반납 예정일, 연체)을 정하는 기관 시간대
    library_timezone: str = "Asia/Seoul"

    # 비밀번호 해시(scrypt) 비용. 테스트에서만 낮춘다.
    password_scrypt_n: int = 2**14

    # 시드 계정 비밀번호. 시드를 실행할 때만 필요하다.
    seed_admin_password: str | None = None
    seed_kiosk_password: str | None = None

    # YES24 Open API. 키는 서지정보 채움 실행에만 쓴다.
    yes24_api_key: SecretStr | None = None
    yes24_base_url: str = "https://apis.yes24.com/v1"

    # LLM. 키가 없어도 서버는 시작하고, 에이전트 실행만 실패한다.
    openai_api_key: SecretStr | None = None
    llm_model: str = "gpt-6-luna"
    llm_effort: str = "low"
    llm_max_tokens: int = 25000  # 추론과 출력을 합친 상한
    llm_timeout_seconds: float = 60.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
