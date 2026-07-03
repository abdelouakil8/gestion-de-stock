from fastapi import FastAPI

from app.api.errors import install_error_handlers
from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging


def _ensure_schema() -> None:
    """First-run bootstrap for packaged installs: create tables when absent.

    Development and upgrades keep using Alembic migrations; this only fires
    on a brand-new database file (ORM metadata — no raw SQL).
    """
    from sqlalchemy import inspect

    from app import models
    from app.db.session import engine

    if "stores" not in inspect(engine).get_table_names():
        models.Base.metadata.create_all(engine)


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
