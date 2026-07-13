"""Sales velocity analysis — turnover rates and days-of-stock estimates.

Velocity = base units sold per day over the analysis window. Days-of-stock =
current stock / velocity (None when velocity is zero). These numbers drive
reorder decisions for a small retailer.
"""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, type_coerce
from sqlalchemy.orm import Session

from app.db.types import Money
from app.models import Category, Product, Sale, SaleItem
from app.schemas.statistics import (
    CategoryTurnover,
    ProductVelocity,
    StockTurnover,
)

_ZERO = Decimal("0.00")


def _base_filter(store_id: UUID, date_from: datetime, date_to: datetime):
    return (
        (Sale.store_id == store_id)
        & Sale.deleted_at.is_(None)
        & SaleItem.deleted_at.is_(None)
        & (Sale.created_at >= date_from)
        & (Sale.created_at <= date_to)
    )


def product_velocity(
    db: Session,
    store_id: UUID,
    date_from: datetime,
    date_to: datetime,
    *,
    limit: int = 20,
    sort: str = "velocity",
) -> list[ProductVelocity]:
    days = max(1, (date_to - date_from).days)
    units_col = func.coalesce(func.sum(SaleItem.quantity * SaleItem.unit_count), 0)
    stmt = (
        select(
            Product.id.label("product_id"),
            Product.name,
            Category.name.label("category_name"),
            units_col.label("units_sold"),
            Product.stock_quantity,
        )
        .join(SaleItem, SaleItem.sale_id == Sale.id)
        .join(Product, Product.id == SaleItem.product_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .where(_base_filter(store_id, date_from, date_to))
        .group_by(Product.id, Product.name, Category.name, Product.stock_quantity)
    )
    rows = db.execute(stmt).all()

    results = []
    for r in rows:
        vel = r.units_sold / days
        dos = r.stock_quantity / vel if vel > 0 else None
        results.append(
            ProductVelocity(
                product_id=r.product_id,
                name=r.name,
                category_name=r.category_name,
                units_sold=r.units_sold,
                velocity=round(vel, 2),
                stock_quantity=r.stock_quantity,
                days_of_stock=round(dos, 1) if dos is not None else None,
            )
        )

    if sort == "days_of_stock":
        results.sort(
            key=lambda p: (
                p.days_of_stock if p.days_of_stock is not None else float("inf")
            )
        )
    else:
        results.sort(key=lambda p: p.velocity, reverse=True)
    return results[:limit]


def stock_turnover(
    db: Session,
    store_id: UUID,
    date_from: datetime,
    date_to: datetime,
) -> StockTurnover:
    days = max(1, (date_to - date_from).days)
    annualize = 365 / days

    cost_expr = type_coerce(
        SaleItem.quantity * SaleItem.unit_count * Product.cost_price, Money()
    )
    stmt = (
        select(
            Category.id.label("category_id"),
            Category.name.label("category_name"),
            func.coalesce(type_coerce(func.sum(cost_expr), Money()), 0).label("cogs"),
            func.coalesce(func.sum(SaleItem.quantity * SaleItem.unit_count), 0).label(
                "units_sold"
            ),
        )
        .join(SaleItem, SaleItem.sale_id == Sale.id)
        .join(Product, Product.id == SaleItem.product_id)
        .outerjoin(Category, Category.id == Product.category_id)
        .where(_base_filter(store_id, date_from, date_to))
        .group_by(Category.id, Category.name)
    )
    rows = db.execute(stmt).all()

    inv_stmt = (
        select(
            Category.id.label("category_id"),
            type_coerce(
                func.coalesce(func.sum(Product.stock_quantity * Product.cost_price), 0),
                Money(),
            ).label("stock_value"),
        )
        .outerjoin(Category, Category.id == Product.category_id)
        .where(
            (Product.store_id == store_id)
            & Product.deleted_at.is_(None)
            & Product.is_active.is_(True)
        )
        .group_by(Category.id)
    )
    inv_rows = {
        r.category_id: Decimal(str(r.stock_value)) for r in db.execute(inv_stmt).all()
    }

    categories = []
    total_cogs = _ZERO
    total_inv = _ZERO
    for r in rows:
        cogs = Decimal(str(r.cogs))
        inv_val = inv_rows.get(r.category_id, _ZERO)
        turnover = float(cogs * annualize / inv_val) if inv_val else 0.0
        categories.append(
            CategoryTurnover(
                category_id=r.category_id,
                name=r.category_name,
                turnover=round(turnover, 1),
                units_sold=r.units_sold,
                avg_stock_value=inv_val,
            )
        )
        total_cogs += cogs
        total_inv += inv_val

    overall = float(total_cogs * annualize / total_inv) if total_inv else 0.0
    categories.sort(key=lambda c: c.turnover, reverse=True)
    return StockTurnover(overall_turnover=round(overall, 1), categories=categories)
