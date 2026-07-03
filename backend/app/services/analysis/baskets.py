"""Basket provider: sale_items -> baskets of product ids.

The bridge between the database and the pure analysis modules: any
algorithm in this package consumes the output of sale_baskets() without
knowing anything about SQLAlchemy."""

from collections import defaultdict
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Sale, SaleItem


def sale_baskets(
    db: Session, store_id: UUID, date_from: datetime, date_to: datetime
) -> list[frozenset[UUID]]:
    """One basket per non-deleted sale in range: the set of product ids."""
    rows = db.execute(
        select(SaleItem.sale_id, SaleItem.product_id)
        .join(Sale, SaleItem.sale_id == Sale.id)
        .where(
            Sale.store_id == store_id,
            Sale.deleted_at.is_(None),
            SaleItem.deleted_at.is_(None),
            Sale.created_at >= date_from,
            Sale.created_at <= date_to,
        )
    ).all()

    by_sale: dict[UUID, set[UUID]] = defaultdict(set)
    for sale_id, product_id in rows:
        by_sale[sale_id].add(product_id)
    return [frozenset(products) for products in by_sale.values()]
