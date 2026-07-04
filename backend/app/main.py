from fastapi import FastAPI

from app.api.errors import install_error_handlers
from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging


def _ensure_schema() -> None:
    """Create-or-migrate the database at startup (dev AND packaged).

    Every schema change ships as an Alembic migration; running them here
    means an existing merchant database is upgraded in place on the first
    launch after an update — no manual `alembic upgrade head` ever.
    """
    from app.db.migrate import prepare_database
    from app.db.session import engine

    prepare_database(engine)


def create_app() -> FastAPI:
    configure_logging()
    _ensure_schema()
    app = FastAPI(title=settings.app_name)
    install_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/")
    def root() -> dict[str, str]:
        """Liveness endpoint — the desktop client polls this at startup."""
        return {"status": "ok", "app": settings.app_name}

    return app


app = create_app()
