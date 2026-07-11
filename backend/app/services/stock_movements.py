"""Read-side queries for the stock movement ledger."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.stock_movement import StockMovement


def list_movements(
    db: Session,
    *,
    store_id: UUID,
    product_id: UUID,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[StockMovement], int]:
    """Return (page, total_count) for a product's movement history, newest first."""
    base = select(StockMovement).where(
        StockMovement.store_id == store_id,
        StockMovement.product_id == product_id,
        StockMovement.deleted_at.is_(None),
    )
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    items = list(
        db.scalars(
            base.order_by(StockMovement.created_at.desc()).limit(limit).offset(offset)
        )
    )
    return items, total
