import sys

from loguru import logger

from app.core.config import RUNTIME_DIR, settings


def configure_logging() -> None:
    """Route application logging through loguru: console + rotating file."""
    logger.remove()
    if sys.stderr is not None:  # absent in a windowed (no-console) build
        logger.add(sys.stderr, level=settings.log_level)
    logger.add(
        RUNTIME_DIR / "logs" / "app.log",
        level=settings.log_level,
        rotation="10 MB",
        retention=10,
        encoding="utf-8",
    )
