"""Administration — factory reset (owner-only, Réglages > zone dangereuse).

Unlike everything else in this application, the reset is a PHYSICAL wipe:
an explicit, PIN-confirmed owner decision to erase the whole business
(equivalent to uninstall + reinstall). Soft-delete rules protect data from
accidents, not from the owner deliberately starting over.
"""

import shutil
from pathlib import Path

from loguru import logger
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Base


def factory_reset(db: Session) -> dict[str, int]:
    """Erase every business row and every stored media file, atomically
    for the database part. Returns per-table deleted-row counts.

    The wipe order is derived from the schema's foreign-key graph:
    ``Base.metadata.sorted_tables`` lists tables parent-first, so iterating it
    reversed deletes children before parents — a foreign-key-safe order that
    stays correct as new tables are added. A hand-maintained list silently
    rots (packagings, stock movements, purchase orders, refunds, reservations,
    … were all missed), and with ``PRAGMA foreign_keys=ON`` (the production
    setting, see db/session.py) a single missed child table makes the entire
    reset fail with a FOREIGN KEY constraint error.
    """
    counts: dict[str, int] = {}
    try:
        for table in reversed(Base.metadata.sorted_tables):
            result = db.execute(table.delete())
            counts[table.name] = result.rowcount or 0
        db.commit()
    except Exception:
        db.rollback()
        raise

    media_root = Path(settings.media_dir)
    if media_root.is_dir():
        shutil.rmtree(media_root, ignore_errors=True)

    logger.warning("FACTORY RESET executed | rows={}", counts)
    return counts
