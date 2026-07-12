"""Read-side queries for the stock movement ledger."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Category, Product
from app.models.stock_movement import MovementType, StockMovement


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


def list_all_movements(
    db: Session,
    *,
    store_id: UUID,
    product_id: UUID | None = None,
    category_id: UUID | None = None,
    movement_type: MovementType | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Store-wide movement ledger, newest first, with the product name /
    barcode / category joined in server-side (no N+1 lookups on the client).

    Returns (page, total_count). Every filter is optional; date_to is an
    exclusive upper bound, matching the rest of the app.
    """
    conditions = [
        StockMovement.store_id == store_id,
        StockMovement.deleted_at.is_(None),
    ]
    if product_id is not None:
        conditions.append(StockMovement.product_id == product_id)
    if movement_type is not None:
        conditions.append(StockMovement.movement_type == movement_type)
    if category_id is not None:
        conditions.append(Product.category_id == category_id)
    if date_from is not None:
        conditions.append(StockMovement.created_at >= date_from)
    if date_to is not None:
        conditions.append(StockMovement.created_at < date_to)

    total = (
        db.scalar(
            select(func.count())
            .select_from(StockMovement)
            .join(Product, StockMovement.product_id == Product.id)
            .where(*conditions)
        )
        or 0
    )

    rows = db.execute(
        select(
            StockMovement,
            Product.name.label("product_name"),
            Product.barcode.label("product_barcode"),
            Category.name.label("category_name"),
        )
        .join(Product, StockMovement.product_id == Product.id)
        .outerjoin(Category, Product.category_id == Category.id)
        .where(*conditions)
        .order_by(StockMovement.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()

    items = [
        {
            "id": mv.id,
            "created_at": mv.created_at,
            "store_id": mv.store_id,
            "product_id": mv.product_id,
            "product_name": product_name,
            "product_barcode": product_barcode,
            "category_name": category_name,
            "movement_type": mv.movement_type,
            "quantity_delta": mv.quantity_delta,
            "quantity_after": mv.quantity_after,
            "reference_id": mv.reference_id,
            "reason": mv.reason,
            "note": mv.note,
        }
        for mv, product_name, product_barcode, category_name in rows
    ]
    return items, total
