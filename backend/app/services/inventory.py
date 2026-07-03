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

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.exceptions import InsufficientStockError, InvalidQuantityError
from app.models import Product


def decrement_stock(db: Session, product: Product, quantity: int) -> None:
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


def increment_stock(db: Session, product_id: UUID, quantity: int) -> None:
    """Add stock (restock/correction). Does not commit."""
    if quantity < 1:
        raise InvalidQuantityError(quantity)

    db.execute(
        update(Product)
        .where(Product.id == product_id, Product.deleted_at.is_(None))
        .values(stock_quantity=Product.stock_quantity + quantity)
        .execution_options(synchronize_session=False)
    )
