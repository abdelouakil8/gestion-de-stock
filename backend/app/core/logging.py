import sys

from loguru import logger

from app.core.config import PROJECT_ROOT, settings


def configure_logging() -> None:
    """Route application logging through loguru: console + rotating file."""
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level)
    logger.add(
        PROJECT_ROOT / "logs" / "app.log",
        level=settings.log_level,
        rotation="10 MB",
        retention=10,
        encoding="utf-8",
    )
