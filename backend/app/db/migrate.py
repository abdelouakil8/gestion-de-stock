"""Programmatic Alembic upgrades — run at EVERY startup (dev and packaged).

Root-cause fix for the "internal error after an update" class of bugs: a
database created by an earlier phase keeps its old schema unless someone
runs `alembic upgrade head` by hand. Nobody will on a merchant's machine,
so the app does it itself before serving a single request.

Cases handled:
- brand-new database            -> create_all + stamp head (fast path)
- alembic-managed database      -> upgrade head
- legacy create_all database    -> detect its generation, stamp the
  matching revision, then upgrade head (packaged builds bootstrapped via
  ORM metadata before this module existed and have no alembic_version).
"""

import sys
from pathlib import Path

from alembic.config import Config
from loguru import logger
from sqlalchemy import inspect
from sqlalchemy.engine import Engine

from alembic import command

# Revision markers used to stamp legacy create_all databases (no
# alembic_version row) at the correct generation before running upgrade.
# When adding a phase, add its revision here AND extend the marker-column
# detection below — the two must move together.
_PHASE5_REV = "b41c92d7e310"
_PHASE6_REV = "c9a1e4b7d2f0"
_PHASE7_REV = "d4f8a1c07e2b"
_PHASE8_REV = "e5b2c9f4a3d1"


def _base_dir() -> Path:
    """Directory containing alembic.ini and the alembic/ scripts."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)  # bundled as data files by the .spec
    return Path(__file__).resolve().parents[2]  # backend/


def alembic_config() -> Config:
    base = _base_dir()
    cfg = Config(str(base / "alembic.ini"))
    cfg.set_main_option("script_location", str(base / "alembic"))
    return cfg


def prepare_database(engine: Engine) -> None:
    """Create-or-migrate the schema to head. Raises loudly on failure —
    serving requests against a wrong schema is worse than not starting."""
    from app import models

    cfg = alembic_config()
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())

    if "stores" not in tables:
        logger.info("Database bootstrap: creating schema at head")
        models.Base.metadata.create_all(engine)
        command.stamp(cfg, "head")
        return

    if "alembic_version" not in tables:
        # Legacy create_all database: infer its generation from a marker,
        # stamp it, then fall through to the normal upgrade. Regression note:
        # each phase adds ONE marker — never rename or drop it in a later
        # phase, or the newer branch of this if/elif would mis-detect an
        # older DB as newer.
        #   phase 8 marker: product_packagings table exists (cleanest — the
        #                   whole feature is a new table)
        #   phase 7 marker: products.search_text
        #   phase 6 marker: products.price_detail
        #   earlier       : none -> phase 5
        product_columns = {c["name"] for c in inspector.get_columns("products")}
        if "suppliers" in tables:
            revision = "head"
        elif "sale_sequences" in tables:
            revision = "a1b2c3d4e5f6"
        elif "refunds" in tables:
            revision = "f7a3b2c9d4e6"
        elif "product_packagings" in tables:
            revision = _PHASE8_REV
        elif "search_text" in product_columns:
            revision = _PHASE7_REV
        elif "price_detail" in product_columns:
            revision = _PHASE6_REV
        else:
            revision = _PHASE5_REV
        logger.warning(
            "Database has no alembic_version — stamping {} before upgrade",
            revision,
        )
        command.stamp(cfg, revision)

    logger.info("Running database migrations (alembic upgrade head)")
    command.upgrade(cfg, "head")
