from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import lru_cache
from typing import Any

from pydantic import SecretStr
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict


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


# `.env`와 환경변수에서 읽는 필드. 비밀이거나 설치마다 값이 다른 것만 여기 둔다.
# 이 밖의 필드는 코드 기본값만 쓰고, 같은 이름의 환경변수·`.env` 키는 무시한다.
# 새 필드의 기본은 코드값이다. 설치마다 달라야 하거나 비밀일 때만 여기에 더하고
# `.env.example`에도 적는다.
ENV_FIELDS = frozenset(
    {
        "database_url",
        "test_database_url",
        "yes24_api_key",
        "library_bigdata_key",
        "kakao_rest_api_key",
        "openai_api_key",
        "seed_admin_password",
        "seed_kiosk_password",
        "embedding_base_url",
        "embedding_query_enabled",
    }
)


class _EnvFieldsOnly(PydanticBaseSettingsSource):
    """안쪽 소스가 준 값 가운데 `ENV_FIELDS`에 있는 필드만 통과시킨다."""

    def __init__(self, settings_cls: type[BaseSettings], inner: PydanticBaseSettingsSource) -> None:
        super().__init__(settings_cls)
        self._inner = inner

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        return self._inner.get_field_value(field, field_name)

    def __call__(self) -> dict[str, Any]:
        return {k: v for k, v in self._inner().items() if k in ENV_FIELDS}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # 직접 준 값(테스트·평가)은 모든 필드에 반영하고, 환경변수와 `.env`는 환경 필드만 읽는다.
        return (
            init_settings,
            _EnvFieldsOnly(settings_cls, env_settings),
            _EnvFieldsOnly(settings_cls, dotenv_settings),
        )

    # ---- 환경 값: `.env`와 환경변수에서 읽는다 (ENV_FIELDS) ----

    database_url: str
    test_database_url: str | None = None

    # 시드 계정 비밀번호. 시드를 실행할 때만 필요하다.
    seed_admin_password: str | None = None
    seed_kiosk_password: str | None = None

    # 공식 서지의 출처 셋(YES24, 정보나루, 카카오). 키는 서지정보 채움과 실험 장서 받기에만 쓴다.
    yes24_api_key: SecretStr | None = None
    library_bigdata_key: SecretStr | None = None
    kakao_rest_api_key: SecretStr | None = None

    # LLM 키. 키가 없어도 서버는 시작하고, 에이전트 실행만 실패한다.
    openai_api_key: SecretStr | None = None

    # 로컬 임베딩 서버(TEI) 주소. 꺼져 있어도 서버와 테스트는 돌고, 임베딩 적재만 멈춘다.
    # docker-compose.yml의 EMBEDDING_PORT와 맞춘다.
    embedding_base_url: str = "http://localhost:8090"
    # 서비스 중 질의 인코딩(AI 사서 주제로 찾기). 서버를 안 띄우는 환경에서는 끈다.
    embedding_query_enabled: bool = True

    # ---- 코드값: 환경변수와 `.env`를 읽지 않는다 ----

    # 인증 토큰 만료 시간. 키오스크는 도서관 PC에 켜 두는 화면이라 길다.
    admin_token_hours: int = 12
    kiosk_token_hours: int = 720
    # 키오스크의 회원 로그인 세션. 화면의 이용 상한(로그인부터 180초)과 같은 3분이다.
    member_session_minutes: int = 3
    # 회원이 담은 책: 담은 시각부터 보관하는 시간과 한 회원이 담을 수 있는 권수
    basket_keep_hours: int = 3
    basket_limit: int = 10

    # "오늘"(대출일, 반납 예정일, 연체)을 정하는 기관 시간대. 서울로 고정한다.
    library_timezone: str = "Asia/Seoul"

    # 비밀번호 해시(scrypt) 비용. 테스트에서만 객체의 값을 낮춘다.
    password_scrypt_n: int = 2**14

    # 외부 서지 API 주소. 정보나루는 키를 쿼리 파라미터로만 받는다. 그래서 https로 부르고
    # URL을 로그에 남기지 않는다.
    yes24_base_url: str = "https://apis.yes24.com/v1"
    data4library_base_url: str = "https://data4library.kr/api"
    kakao_base_url: str = "https://dapi.kakao.com"

    # LLM. 모델별 가격은 LLM_PRICES를 본다. 모델은 평가 결과의 기준이라 설치마다 바꾸지 않는다.
    llm_model: str = "gpt-6-luna"
    llm_effort: str = "low"
    llm_max_tokens: int = 25000  # 추론과 출력을 합친 상한
    llm_timeout_seconds: float = 60.0

    # AI 사서 대화. 무입력 시간이 지나면 세션이 끝나고 메시지를 지운다.
    librarian_session_idle_minutes: int = 5
    librarian_max_turns: int = 20  # 한 세션의 턴 수
    librarian_daily_run_limit: int = 500  # 기관별 하루 실행 수 (기관 시간대 기준)
    # 운영 에이전트 대화(관리자). 턴 상한은 AI 사서와 같은 값을 쓴다. 실행 수는 따로 센다.
    admin_session_idle_minutes: int = 30
    admin_daily_run_limit: int = 200

    # 임베딩 모델. docker-compose.yml의 embedder와 같은 값이어야 한다(테스트가 비교하고
    # 서버의 `check()`가 막는다). 벡터 열의 차원은 `app/central/models.py`의 EMBEDDING_DIM이다.
    embedding_model: str = "dragonkue/snowflake-arctic-embed-l-v2.0-ko"
    embedding_max_tokens: int = 512  # 넘는 입력은 앞부분만 인코딩한다. 바꾸면 --full로 다시 적재
    # 한 번에 인코딩할 권수. CPU ONNX에서는 배치가 클수록 느리다(4가 1과 같고 32보다 약 18% 빠름).
    # TEI의 클라이언트 배치 한도(기본 32)를 넘지 않게 둔다
    embedding_batch_size: int = 4
    embedding_timeout_seconds: float = 600.0  # CPU에서 512토큰 32권에 2분쯤 걸린다
    # 서비스 중 질의 인코딩. 꺼지거나 느리면 키워드 순위로 내려간다.
    embedding_query_timeout_seconds: float = 2.0  # 질의 하나는 CPU에서 약 0.2초
    embedding_query_pause_seconds: float = 30.0  # 실패 뒤 이 시간 동안 서버를 부르지 않는다


_unknown_env_fields = ENV_FIELDS - set(Settings.model_fields)
if _unknown_env_fields:
    raise RuntimeError(f"ENV_FIELDS에 없는 설정 필드: {sorted(_unknown_env_fields)}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
