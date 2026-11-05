from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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


@lru_cache
def get_settings() -> Settings:
    return Settings()
