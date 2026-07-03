import os
import sys
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# core/ -> app/ -> backend/ -> project root
PROJECT_ROOT = Path(__file__).resolve().parents[3]

if getattr(sys, "frozen", False):
    # Packaged build (PyInstaller): the install dir (Program Files) is
    # read-only, so mutable state lives in the user profile instead.
    RUNTIME_DIR = (
        Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "GestionStockPOS"
    )
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
else:
    RUNTIME_DIR = PROJECT_ROOT


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=RUNTIME_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Gestion Stock POS"
    api_host: str = "127.0.0.1"
    api_port: int = 8765
    database_url: str = f"sqlite:///{(RUNTIME_DIR / 'data' / 'pos.db').as_posix()}"
    # Root of stored media (product images). image_path columns are
    # RELATIVE to this directory — never absolute, never user-provided.
    media_dir: Path = RUNTIME_DIR / "media"
    log_level: str = "INFO"
    # PBKDF2 hash of the owner PIN (set via scripts/set_pin.py, never plaintext).
    pin_hash: str | None = None

    @field_validator("api_host")
    @classmethod
    def _loopback_only(cls, value: str) -> str:
        # Security invariant: the local API is never exposed on the network.
        if not value.startswith("127."):
            raise ValueError("API_HOST must be a loopback address (127.x.x.x)")
        return value


settings = Settings()
