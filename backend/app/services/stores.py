"""CRUD for stores. No business logic — Phase 2 owns the rules."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Store
from app.schemas.store import StoreCreate


def create_store(db: Session, data: StoreCreate) -> Store:
    store = Store(**data.model_dump())
    db.add(store)
    db.commit()
    db.refresh(store)
    return store


def get_store(db: Session, store_id: UUID) -> Store | None:
    """Fetch one store; soft-deleted rows are excluded by default."""
    return db.scalar(
        select(Store).where(Store.id == store_id, Store.deleted_at.is_(None))
    )


def list_stores(db: Session) -> list[Store]:
    return list(
        db.scalars(
            select(Store).where(Store.deleted_at.is_(None)).order_by(Store.name)
        )
    )


def soft_delete_store(db: Session, store_id: UUID) -> Store | None:
    store = get_store(db, store_id)
    if store is not None:
        store.deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(store)
    return store
