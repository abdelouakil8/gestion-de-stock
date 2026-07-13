"""Profitability analysis — per-product margin ranking and margin tiers.

Cost is derived from the current Product.cost_price (the store's landed cost)
times the base units sold. This matches the convention used everywhere else in
the statistics layer — no historical cost tracking.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, type_coerce
from sqlalchemy.orm import Session

from app.db.types import Money
from app.models import Category, Product, Sale, SaleItem
from app.schemas.statistics import (
    MarginAnalysis,
    MarginTier,
    ProductProfitability,
)

_ZERO = Decimal("0.00")

_MARGIN_TIERS = [
    ("< 10 %", 0, 10),
    ("10 – 25 %", 10, 25),
    ("25 – 50 %", 25, 50),
    ("> 50 %", 50, 101),
]


def _base_filter(store_id: UUID, date_from: datetime, date_to: datetime):
    return (
        (Sale.store_id == store_id)
        & Sale.deleted_at.is_(None)
        & SaleItem.deleted_at.is_(None)
        & (Sale.created_at >= date_from)
        & (Sale.created_at <= date_to)
    )


def product_profitability(
    db: Session,
    store_id: UUID,
    date_from: datetime,
    date_to: datetime,
    *,
    limit: int = 20,
    sort: str = "profit",
) -> list[ProductProfitability]:
    cost_expr = type_coerce(
        SaleItem.quantity * SaleItem.unit_count * Product.cost_price, Money()
    )
    revenue_col = func.coalesce(type_coerce(func.sum(SaleItem.line_total), Money()), 0)
    cost_col = func.coalesce(type_coerce(func.sum(cost_expr), Money()), 0)

    stmt = (
        select(
            Product.id.label("product_id"),
            Product.name,
            Category.name.label("category_name"),
            revenue_col.label("revenue"),
            cost_col.label("cost"),
        )
        .join(SaleItem, SaleItem.sale_id == Sale.id)
        .join(Product, Product.id == SaleItem.product_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .where(_base_filter(store_id, date_from, date_to))
        .group_by(Product.id, Product.name, Category.name)
    )
    rows = db.execute(stmt).all()

    total_profit = sum(
        (Decimal(str(r.revenue)) - Decimal(str(r.cost)) for r in rows), _ZERO
    )

    results = []
    for r in rows:
        revenue = Decimal(str(r.revenue))
        cost = Decimal(str(r.cost))
        profit = revenue - cost
        margin = float(profit / revenue * 100) if revenue else 0.0
        contribution = float(profit / total_profit * 100) if total_profit else 0.0
        results.append(
            ProductProfitability(
                product_id=r.product_id,
                name=r.name,
                category_name=r.category_name,
                revenue=revenue,
                cost=cost,
                profit=profit,
                margin_pct=round(margin, 1),
                contribution_pct=round(contribution, 1),
            )
        )

    if sort == "margin_pct":
        results.sort(key=lambda p: p.margin_pct)
    else:
        results.sort(key=lambda p: p.profit, reverse=True)
    return results[:limit]


def margin_analysis(
    db: Session,
    store_id: UUID,
    date_from: datetime,
    date_to: datetime,
) -> MarginAnalysis:
    all_products = product_profitability(db, store_id, date_from, date_to, limit=10_000)
    total_revenue = sum((p.revenue for p in all_products), _ZERO)
    total_profit = sum((p.profit for p in all_products), _ZERO)
    blended = float(total_profit / total_revenue * 100) if total_revenue else 0.0

    tiers = []
    for label, low, high in _MARGIN_TIERS:
        bucket = [p for p in all_products if low <= p.margin_pct < high]
        tiers.append(
            MarginTier(
                tier=label,
                product_count=len(bucket),
                revenue=sum((p.revenue for p in bucket), _ZERO),
                profit=sum((p.profit for p in bucket), _ZERO),
            )
        )
    return MarginAnalysis(blended_margin_pct=round(blended, 1), tiers=tiers)
