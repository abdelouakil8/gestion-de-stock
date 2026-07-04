"""Administration — factory reset (owner-only, Réglages > zone dangereuse).

Unlike everything else in this application, the reset is a PHYSICAL wipe:
an explicit, PIN-confirmed owner decision to erase the whole business
(equivalent to uninstall + reinstall). Soft-delete rules protect data from
accidents, not from the owner deliberately starting over.
"""

import shutil
from pathlib import Path

from loguru import logger
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Category,
    Customer,
    Payment,
    Product,
    Sale,
    SaleItem,
    Store,
    StoreSettings,
)

# Children before parents — foreign-key-safe wipe order.
_WIPE_ORDER = [
    Payment,
    SaleItem,
    Sale,
    StoreSettings,
    Customer,
    Product,
    Category,
    Store,
]


def factory_reset(db: Session) -> dict[str, int]:
    """Erase every business row and every stored media file, atomically
    for the database part. Returns per-table deleted-row counts."""
    counts: dict[str, int] = {}
    try:
        for model in _WIPE_ORDER:
            result = db.execute(delete(model))
            counts[model.__tablename__] = result.rowcount or 0
        db.commit()
    except Exception:
        db.rollback()
        raise

    media_root = Path(settings.media_dir)
    if media_root.is_dir():
        shutil.rmtree(media_root, ignore_errors=True)

    logger.warning("FACTORY RESET executed | rows={}", counts)
    return counts
