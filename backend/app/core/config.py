from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# core/ -> app/ -> backend/ -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Gestion Stock POS"
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    database_url: str = f"sqlite:///{(PROJECT_ROOT / 'data' / 'pos.db').as_posix()}"
    log_level: str = "INFO"

    @field_validator("api_host")
    @classmethod
    def _loopback_only(cls, value: str) -> str:
        # Security invariant: the local API is never exposed on the network.
        if not value.startswith("127."):
            raise ValueError("API_HOST must be a loopback address (127.x.x.x)")
        return value


settings = Settings()
