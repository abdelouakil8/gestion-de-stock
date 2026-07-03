"""Alerts feed for the notifications screen (single polled endpoint).

Two alert families:
- low stock: active products at or below their per-product threshold;
- outstanding credits: sales with money still owed, joined with the
  customer, sorted oldest debt first (the merchant chases old money).
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select, type_coerce
from sqlalchemy.orm import Session

from app.db.types import Money
from app.models import Customer, Product, Sale
from app.schemas.alerts import AlertsResponse, AlertsSummary, LowStockProduct
from app.schemas.sale import OutstandingSale


def _utc_naive_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def low_stock_products(db: Session, store_id: UUID) -> list[LowStockProduct]:
    rows = db.execute(
        select(
            Product.id.label("product_id"),
            Product.name,
            Product.barcode,
            Product.stock_quantity,
            Product.low_stock_threshold,
        )
        .where(
            Product.store_id == store_id,
            Product.deleted_at.is_(None),
            Product.is_active.is_(True),
            Product.stock_quantity <= Product.low_stock_threshold,
        )
        .order_by(Product.stock_quantity, Product.name)
    ).all()
    return [LowStockProduct.model_validate(row) for row in rows]


def outstanding_credits(
    db: Session, store_id: UUID, now: datetime | None = None
) -> list[OutstandingSale]:
    """Every sale with balance > 0, oldest first, with the debt's age."""
    now = now if now is not None else _utc_naive_now()
    rows = db.execute(
        select(Sale, Customer)
        .outerjoin(Customer, Sale.customer_id == Customer.id)
        .where(
            Sale.store_id == store_id,
            Sale.deleted_at.is_(None),
            Sale.paid_amount < Sale.total_amount,
        )
        .order_by(Sale.created_at)
    ).all()

    results = []
    for sale, customer in rows:
        created = sale.created_at
        if created.tzinfo is not None:  # PostgreSQL returns aware datetimes
            created = created.astimezone(UTC).replace(tzinfo=None)
        results.append(
            OutstandingSale(
                sale_id=sale.id,
                created_at=sale.created_at,
                customer_id=sale.customer_id,
                customer_name=customer.name if customer else None,
                customer_phone=customer.phone if customer else None,
                total_amount=sale.total_amount,
                paid_amount=sale.paid_amount,
                balance=sale.total_amount - sale.paid_amount,
                age_days=max(0, (now - created).days),
            )
        )
    return results


def get_alerts(
    db: Session, store_id: UUID, now: datetime | None = None
) -> AlertsResponse:
    low_stock = low_stock_products(db, store_id)
    credits = outstanding_credits(db, store_id, now=now)

    outstanding_total = db.scalar(
        select(
            type_coerce(
                func.coalesce(func.sum(Sale.total_amount - Sale.paid_amount), 0),
                Money(),
            )
        ).where(
            Sale.store_id == store_id,
            Sale.deleted_at.is_(None),
            Sale.paid_amount < Sale.total_amount,
        )
    )

    return AlertsResponse(
        summary=AlertsSummary(
            low_stock_count=len(low_stock),
            outstanding_credits_count=len(credits),
            outstanding_total=outstanding_total,
        ),
        low_stock=low_stock,
        outstanding_credits=credits,
    )
