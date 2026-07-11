"""Inventory rules — atomic stock movements.

The decrement is a single conditional UPDATE (`... SET stock = stock - :q
WHERE id = :id AND stock >= :q`): the check and the write are one atomic
statement at the database level, so two near-simultaneous sales competing
for the last units can never both succeed — the loser's UPDATE matches zero
rows and the sale is rejected. A CHECK constraint (stock_quantity >= 0)
backstops this at the schema level. Never check-then-write in Python.

Functions here do NOT commit: the caller (checkout) owns the transaction so
that price checks, stock decrements and the Sale insert commit atomically.
"""

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.exceptions import InsufficientStockError, InvalidQuantityError
from app.models import Product
from app.models.stock_movement import MovementType, StockMovement


def record_movement(
    db: Session,
    *,
    store_id: UUID,
    product_id: UUID,
    delta: int,
    after: int,
    movement_type: MovementType,
    ref_id: UUID | None = None,
    note: str | None = None,
) -> None:
    """Append a StockMovement row. Does NOT commit — caller owns the transaction."""
    db.add(
        StockMovement(
            store_id=store_id,
            product_id=product_id,
            movement_type=movement_type,
            quantity_delta=delta,
            quantity_after=after,
            reference_id=ref_id,
            note=note,
        )
    )


def decrement_stock(
    db: Session, product: Product, quantity: int, sale_id: UUID | None = None
) -> None:
    """Atomically take `quantity` units, or raise without side effects."""
    if quantity < 1:
        raise InvalidQuantityError(quantity)

    result = db.execute(
        update(Product)
        .where(
            Product.id == product.id,
            Product.deleted_at.is_(None),
            Product.stock_quantity >= quantity,
        )
        .values(stock_quantity=Product.stock_quantity - quantity)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise InsufficientStockError(product_name=product.name, requested=quantity)
    db.expire(product, ["stock_quantity"])

    quantity_after = (
        db.scalar(select(Product.stock_quantity).where(Product.id == product.id)) or 0
    )
    record_movement(
        db,
        store_id=product.store_id,
        product_id=product.id,
        delta=-quantity,
        after=quantity_after,
        movement_type=MovementType.sale,
        ref_id=sale_id,
    )


def increment_stock(
    db: Session,
    product_id: UUID,
    quantity: int,
    ref_id: UUID | None = None,
    movement_type: MovementType = MovementType.refund,
) -> None:
    """Add stock (restock/correction). Does not commit."""
    if quantity < 1:
        raise InvalidQuantityError(quantity)

    db.execute(
        update(Product)
        .where(Product.id == product_id, Product.deleted_at.is_(None))
        .values(stock_quantity=Product.stock_quantity + quantity)
        .execution_options(synchronize_session=False)
    )

    row = db.execute(
        select(Product.store_id, Product.stock_quantity).where(Product.id == product_id)
    ).one_or_none()
    if row is not None:
        record_movement(
            db,
            store_id=row.store_id,
            product_id=product_id,
            delta=quantity,
            after=row.stock_quantity,
            movement_type=movement_type,
            ref_id=ref_id,
        )
