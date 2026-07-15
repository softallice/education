# app/config.py — docpilot 런타임 설정 (전부 환경변수에서 읽는다, 12-Factor III)
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """환경변수/.env 에서 설정을 읽는다. 비밀은 코드에 하드코딩하지 않는다."""

    # DB 접속 정보. compose 네트워크에서는 host 가 서비스명 `db`.
    database_url: str = "postgresql+psycopg://docpilot:docpilot@db:5432/docpilot"

    # 애플리케이션 메타
    app_name: str = "docpilot"
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """설정 싱글턴 (.env/환경변수를 최초 1회만 읽는다)."""
    return Settings()
