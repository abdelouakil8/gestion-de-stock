"""Statistics — revenue/profit/top-products, per-product periods, overview.

Deliberately self-contained: analysis modules (e.g. Apriori market-basket
analysis) live as sibling modules under app/services/analysis/ without
touching this one.

All monetary aggregation happens on the Money column type (BIGINT minor
units), so SQL SUMs are exact integer arithmetic — no float drift.

Timezone contract: created_at is stored as naive UTC (CURRENT_TIMESTAMP).
Calendar periods ("today", "this month"…) follow the store timezone = the
local machine; boundaries are computed locally then converted to naive UTC
with to_utc_naive() before touching SQL.
"""

from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from sqlalchemy import desc, func, select, type_coerce
from sqlalchemy.orm import Session

from app.db.types import Money
from app.models import Product, Sale, SaleItem
from app.schemas.statistics import (
    OverviewPeriod,
    OverviewStats,
    PeriodStats,
    ProductStats,
    StatsSummary,
    TopProduct,
)


def to_utc_naive(local_dt: datetime) -> datetime:
    """Naive local datetime -> naive UTC datetime (storage convention)."""
    return local_dt.astimezone().astimezone(UTC).replace(tzinfo=None)


def _sale_items_in_range(store_id: UUID, date_from: datetime, date_to: datetime):
    """Shared filter: non-deleted sale items of non-deleted sales in range."""
    return (
        (Sale.store_id == store_id)
        & Sale.deleted_at.is_(None)
        & SaleItem.deleted_at.is_(None)
        & (Sale.created_at >= date_from)
        & (Sale.created_at <= date_to)
    )


def sales_summary(
    db: Session, store_id: UUID, date_from: datetime, date_to: datetime
) -> StatsSummary:
    row = db.execute(
        select(
            type_coerce(func.coalesce(func.sum(SaleItem.line_total), 0), Money()).label(
                "revenue"
            ),
            type_coerce(
                func.coalesce(
                    func.sum(
                        SaleItem.line_total
                        - Product.cost_price
                        * SaleItem.quantity
                        * SaleItem.unit_count
                    ),
                    0,
                ),
                Money(),
            ).label("gross_profit"),
            func.count(func.distinct(SaleItem.sale_id)).label("sales_count"),
        )
        .join(Sale, SaleItem.sale_id == Sale.id)
        .join(Product, SaleItem.product_id == Product.id)
        .where(_sale_items_in_range(store_id, date_from, date_to))
    ).one()

    return StatsSummary(
        revenue=row.revenue,
        gross_profit=row.gross_profit,
        sales_count=row.sales_count,
        date_from=date_from,
        date_to=date_to,
    )


def top_products(
    db: Session,
    store_id: UUID,
    date_from: datetime,
    date_to: datetime,
    limit: int = 10,
) -> list[TopProduct]:
    rows = db.execute(
        select(
            Product.id.label("product_id"),
            Product.name.label("name"),
            # Base units: a package counts as quantity * unit_count units.
            func.sum(SaleItem.quantity * SaleItem.unit_count).label("quantity_sold"),
            type_coerce(func.sum(SaleItem.line_total), Money()).label("revenue"),
        )
        .join(Sale, SaleItem.sale_id == Sale.id)
        .join(Product, SaleItem.product_id == Product.id)
        .where(_sale_items_in_range(store_id, date_from, date_to))
        .group_by(Product.id, Product.name)
        .order_by(desc("quantity_sold"), Product.name)
        .limit(limit)
    ).all()

    return [TopProduct.model_validate(row) for row in rows]


# ------------------------------------------------- Phase 6: period stats


def _range_summary(
    db: Session,
    store_id: UUID,
    date_from: datetime | None,
    date_to: datetime,
    product_id: UUID | None = None,
):
    """Units/revenue/profit/sales_count over [date_from, date_to) in UTC.

    Exclusive upper bound so adjacent calendar periods never overlap.
    date_from=None means all-time (no lower bound)."""
    conditions = [
        Sale.store_id == store_id,
        Sale.deleted_at.is_(None),
        SaleItem.deleted_at.is_(None),
        Sale.created_at < date_to,
    ]
    if date_from is not None:
        conditions.append(Sale.created_at >= date_from)
    if product_id is not None:
        conditions.append(SaleItem.product_id == product_id)

    return db.execute(
        select(
            # Base units: a package counts as quantity * unit_count units.
            func.coalesce(
                func.sum(SaleItem.quantity * SaleItem.unit_count), 0
            ).label("units_sold"),
            type_coerce(func.coalesce(func.sum(SaleItem.line_total), 0), Money()).label(
                "revenue"
            ),
            type_coerce(
                func.coalesce(
                    func.sum(
                        SaleItem.line_total
                        - Product.cost_price
                        * SaleItem.quantity
                        * SaleItem.unit_count
                    ),
                    0,
                ),
                Money(),
            ).label("profit"),
            func.count(func.distinct(SaleItem.sale_id)).label("sales_count"),
        )
        .join(Sale, SaleItem.sale_id == Sale.id)
        .join(Product, SaleItem.product_id == Product.id)
        .where(*conditions)
    ).one()


def product_stats(
    db: Session, store_id: UUID, product_id: UUID, now: datetime | None = None
) -> ProductStats | None:
    """Units sold, revenue and profit for one product over the standard
    windows: today (local calendar day), rolling 7/30/365 days, all-time."""
    product = db.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.store_id == store_id,
            Product.deleted_at.is_(None),
        )
    )
    if product is None:
        return None

    now_local = now if now is not None else datetime.now()
    upper = to_utc_naive(now_local)
    windows: list[tuple[str, datetime | None]] = [
        ("today", to_utc_naive(datetime.combine(now_local.date(), time.min))),
        ("last_7_days", to_utc_naive(now_local - timedelta(days=7))),
        ("last_30_days", to_utc_naive(now_local - timedelta(days=30))),
        ("last_365_days", to_utc_naive(now_local - timedelta(days=365))),
        ("all_time", None),
    ]

    periods = []
    for label, lower in windows:
        row = _range_summary(db, store_id, lower, upper, product_id=product_id)
        periods.append(
            PeriodStats(
                period=label,
                date_from=lower,
                date_to=upper,
                units_sold=row.units_sold,
                revenue=row.revenue,
                profit=row.profit,
            )
        )
    return ProductStats(product_id=product.id, name=product.name, periods=periods)


def _calendar_bounds(
    now_local: datetime,
) -> list[tuple[str, datetime, datetime, datetime]]:
    """(period, prev_start, current_start, current_end) in LOCAL time.

    prev period = [prev_start, current_start); current = [current_start,
    current_end). Weeks start on Monday (French convention)."""
    today = datetime.combine(now_local.date(), time.min)

    day_start = today
    week_start = today - timedelta(days=today.weekday())
    month_start = today.replace(day=1)
    year_start = today.replace(month=1, day=1)

    prev_month_start = (month_start - timedelta(days=1)).replace(day=1)
    return [
        (
            "today",
            day_start - timedelta(days=1),
            day_start,
            day_start + timedelta(days=1),
        ),
        (
            "this_week",
            week_start - timedelta(days=7),
            week_start,
            week_start + timedelta(days=7),
        ),
        (
            "this_month",
            prev_month_start,
            month_start,
            (month_start + timedelta(days=32)).replace(day=1),
        ),
        (
            "this_year",
            year_start.replace(year=year_start.year - 1),
            year_start,
            year_start.replace(year=year_start.year + 1),
        ),
    ]


def overview(db: Session, store_id: UUID, now: datetime | None = None) -> OverviewStats:
    """Revenue/profit/sales count for today / this week / this month / this
    year (calendar periods, store timezone = local machine), each paired
    with the full previous period for comparison."""
    now_local = now if now is not None else datetime.now()

    periods = []
    for label, prev_start, cur_start, cur_end in _calendar_bounds(now_local):
        prev_lo, prev_hi = to_utc_naive(prev_start), to_utc_naive(cur_start)
        cur_lo, cur_hi = to_utc_naive(cur_start), to_utc_naive(cur_end)

        current = _range_summary(db, store_id, cur_lo, cur_hi)
        previous = _range_summary(db, store_id, prev_lo, prev_hi)
        periods.append(
            OverviewPeriod(
                period=label,
                current=StatsSummary(
                    revenue=current.revenue,
                    gross_profit=current.profit,
                    sales_count=current.sales_count,
                    date_from=cur_lo,
                    date_to=cur_hi,
                ),
                previous=StatsSummary(
                    revenue=previous.revenue,
                    gross_profit=previous.profit,
                    sales_count=previous.sales_count,
                    date_from=prev_lo,
                    date_to=prev_hi,
                ),
            )
        )
    return OverviewStats(periods=periods)
