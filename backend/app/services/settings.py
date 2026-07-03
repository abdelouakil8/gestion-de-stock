"""Store settings — 1:1 with Store, lazily created with defaults."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError
from app.models import Store, StoreSettings
from app.schemas.settings import SettingsUpdate


def get_settings(db: Session, store_id: UUID) -> StoreSettings:
    """Fetch the store's settings, creating the default row on first use."""
    store = db.scalar(
        select(Store).where(Store.id == store_id, Store.deleted_at.is_(None))
    )
    if store is None:
        raise NotFoundError("boutique", store_id)

    query = select(StoreSettings).where(
        StoreSettings.store_id == store_id, StoreSettings.deleted_at.is_(None)
    )
    row = db.scalar(query)
    if row is None:
        row = StoreSettings(store_id=store_id)
        db.add(row)
        try:
            db.commit()
        except IntegrityError:
            # Two first accesses raced on the unique store_id index —
            # the other request's row won; use it.
            db.rollback()
            row = db.scalar(query)
        else:
            db.refresh(row)
    return row


def update_settings(db: Session, store_id: UUID, data: SettingsUpdate) -> StoreSettings:
    row = get_settings(db, store_id)
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    return row
