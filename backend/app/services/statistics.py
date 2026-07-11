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
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, desc, func, or_, select, type_coerce
from sqlalchemy.orm import Session

from app.db.types import Money
from app.models import Category, Payment, Product, PurchaseOrder, Sale, SaleItem
from app.schemas.statistics import (
    CategoryStat,
    CustomerInsights,
    DailyPoint,
    DeadStockItem,
    FinancialSnapshot,
    HourBucket,
    InventoryStats,
    OverviewPeriod,
    OverviewStats,
    PaymentMethodBreakdown,
    PeriodStats,
    ProductStats,
    SalesPatterns,
    StatsSummary,
    TopProduct,
    WeekdayBucket,
)


def to_utc_naive(local_dt: datetime) -> datetime:
    """Naive local datetime -> naive UTC datetime (storage convention)."""
    return local_dt.astimezone().astimezone(UTC).replace(tzinfo=None)


def from_utc_naive(utc_dt: datetime) -> datetime:
    """Naive UTC datetime (storage) -> naive local datetime.

    Inverse of to_utc_naive: used to bucket sales by the store-local hour and
    weekday, since created_at is stored as naive UTC."""
    return utc_dt.replace(tzinfo=UTC).astimezone().replace(tzinfo=None)


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
                        - Product.cost_price * SaleItem.quantity * SaleItem.unit_count
                    ),
                    0,
                ),
                Money(),
            ).label("gross_profit"),
            func.count(func.distinct(SaleItem.sale_id)).label("sales_count"),
            type_coerce(
                func.coalesce(func.sum(SaleItem.discount_amount), 0), Money()
            ).label("total_discounts"),
        )
        .join(Sale, SaleItem.sale_id == Sale.id)
        .join(Product, SaleItem.product_id == Product.id)
        .where(_sale_items_in_range(store_id, date_from, date_to))
    ).one()

    return StatsSummary(
        revenue=row.revenue,
        gross_profit=row.gross_profit,
        sales_count=row.sales_count,
        total_discounts=row.total_discounts,
        date_from=date_from,
        date_to=date_to,
    )


def top_products(
    db: Session,
    store_id: UUID,
    date_from: datetime,
    date_to: datetime,
    limit: int = 10,
    sort: str = "quantity",
) -> list[TopProduct]:
    """Best sellers over the range. `sort` ∈ {"quantity", "profit"}: rank by
    base units sold (default) or by total gross profit (the most *lucrative*
    products, not just the most numerous)."""
    order_col = "profit" if sort == "profit" else "quantity_sold"
    rows = db.execute(
        select(
            Product.id.label("product_id"),
            Product.name.label("name"),
            # Base units: a package counts as quantity * unit_count units.
            func.sum(SaleItem.quantity * SaleItem.unit_count).label("quantity_sold"),
            type_coerce(func.sum(SaleItem.line_total), Money()).label("revenue"),
            type_coerce(
                func.sum(
                    SaleItem.line_total
                    - Product.cost_price * SaleItem.quantity * SaleItem.unit_count
                ),
                Money(),
            ).label("profit"),
        )
        .join(Sale, SaleItem.sale_id == Sale.id)
        .join(Product, SaleItem.product_id == Product.id)
        .where(_sale_items_in_range(store_id, date_from, date_to))
        .group_by(Product.id, Product.name)
        .order_by(desc(order_col), Product.name)
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
            func.coalesce(func.sum(SaleItem.quantity * SaleItem.unit_count), 0).label(
                "units_sold"
            ),
            type_coerce(func.coalesce(func.sum(SaleItem.line_total), 0), Money()).label(
                "revenue"
            ),
            type_coerce(
                func.coalesce(
                    func.sum(
                        SaleItem.line_total
                        - Product.cost_price * SaleItem.quantity * SaleItem.unit_count
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


def payment_method_breakdown(
    db: Session, store_id: UUID, date_from: datetime, date_to: datetime
) -> list[PaymentMethodBreakdown]:
    """Revenue split by payment method for the date range."""
    rows = db.execute(
        select(
            Payment.payment_method,
            type_coerce(func.sum(Payment.amount), Money()).label("total"),
            func.count().label("count"),
        )
        .join(Sale, Payment.sale_id == Sale.id)
        .where(
            Sale.store_id == store_id,
            Sale.deleted_at.is_(None),
            Payment.deleted_at.is_(None),
            Payment.created_at >= date_from,
            Payment.created_at <= date_to,
        )
        .group_by(Payment.payment_method)
        .order_by(desc("total"))
    ).all()

    return [
        PaymentMethodBreakdown(
            payment_method=row.payment_method,
            total=row.total,
            count=row.count,
        )
        for row in rows
    ]


# --------------------------------------- Phase 12: dashboard analytics


def daily_evolution(
    db: Session, store_id: UUID, date_from: datetime, date_to: datetime
) -> list[DailyPoint]:
    """Revenue and profit per calendar day over the range, zero-filled.

    Missing days are returned as zero so the line chart is continuous. Days
    are bucketed by the stored (UTC) date — a trend view, not an exact
    calendar total."""
    day = func.date(Sale.created_at)
    rows = db.execute(
        select(
            day.label("day"),
            type_coerce(func.coalesce(func.sum(SaleItem.line_total), 0), Money()).label(
                "revenue"
            ),
            type_coerce(
                func.coalesce(
                    func.sum(
                        SaleItem.line_total
                        - Product.cost_price * SaleItem.quantity * SaleItem.unit_count
                    ),
                    0,
                ),
                Money(),
            ).label("profit"),
        )
        .join(Sale, SaleItem.sale_id == Sale.id)
        .join(Product, SaleItem.product_id == Product.id)
        .where(_sale_items_in_range(store_id, date_from, date_to))
        .group_by(day)
    ).all()

    by_day = {str(row.day)[:10]: row for row in rows}
    points: list[DailyPoint] = []
    cursor, last = date_from.date(), date_to.date()
    while cursor <= last:
        row = by_day.get(cursor.isoformat())
        points.append(
            DailyPoint(
                day=cursor,
                revenue=row.revenue if row else Decimal("0.00"),
                profit=row.profit if row else Decimal("0.00"),
            )
        )
        cursor += timedelta(days=1)
    return points


def inventory_stats(db: Session, store_id: UUID) -> InventoryStats:
    """Capital tied up in stock and stock health counts (owner view)."""
    low_stock = (
        (Product.is_active.is_(True))
        & (Product.stock_quantity > 0)
        & (Product.stock_quantity <= Product.low_stock_threshold)
    )
    row = db.execute(
        select(
            type_coerce(
                func.coalesce(func.sum(Product.cost_price * Product.stock_quantity), 0),
                Money(),
            ).label("stock_value_cost"),
            type_coerce(
                func.coalesce(
                    func.sum(Product.price_detail * Product.stock_quantity), 0
                ),
                Money(),
            ).label("stock_value_retail"),
            func.count().label("product_count"),
            func.coalesce(
                func.sum(case((Product.is_active.is_(True), 1), else_=0)), 0
            ).label("active_count"),
            func.coalesce(
                func.sum(case((Product.stock_quantity <= 0, 1), else_=0)), 0
            ).label("out_of_stock_count"),
            func.coalesce(func.sum(case((low_stock, 1), else_=0)), 0).label(
                "low_stock_count"
            ),
        ).where(Product.store_id == store_id, Product.deleted_at.is_(None))
    ).one()

    return InventoryStats(
        stock_value_cost=row.stock_value_cost,
        stock_value_retail=row.stock_value_retail,
        product_count=row.product_count,
        active_count=row.active_count,
        out_of_stock_count=row.out_of_stock_count,
        low_stock_count=row.low_stock_count,
    )


def dead_stock(
    db: Session,
    store_id: UUID,
    days: int = 60,
    limit: int = 20,
    now: datetime | None = None,
) -> list[DeadStockItem]:
    """Active products still in stock that have not sold in `days` days,
    ranked by tied-up capital (cost × units). Never-sold products count too."""
    now_local = now if now is not None else datetime.now()
    now_utc = to_utc_naive(now_local)
    cutoff = to_utc_naive(now_local - timedelta(days=days))

    last_sold = (
        select(
            SaleItem.product_id.label("pid"),
            func.max(Sale.created_at).label("last_sold"),
        )
        .join(Sale, SaleItem.sale_id == Sale.id)
        .where(
            Sale.store_id == store_id,
            Sale.deleted_at.is_(None),
            SaleItem.deleted_at.is_(None),
        )
        .group_by(SaleItem.product_id)
        .subquery()
    )

    rows = db.execute(
        select(
            Product.id.label("product_id"),
            Product.name.label("name"),
            Category.name.label("category_name"),
            Product.image_path.label("image_path"),
            Product.stock_quantity.label("stock_quantity"),
            type_coerce(Product.cost_price * Product.stock_quantity, Money()).label(
                "tied_capital"
            ),
            last_sold.c.last_sold.label("last_sold_at"),
        )
        .outerjoin(last_sold, Product.id == last_sold.c.pid)
        .outerjoin(Category, Product.category_id == Category.id)
        .where(
            Product.store_id == store_id,
            Product.deleted_at.is_(None),
            Product.is_active.is_(True),
            Product.stock_quantity > 0,
            or_(last_sold.c.last_sold.is_(None), last_sold.c.last_sold < cutoff),
        )
        .order_by(desc("tied_capital"), Product.name)
        .limit(limit)
    ).all()

    items: list[DeadStockItem] = []
    for row in rows:
        last = row.last_sold_at
        days_since = None
        if last is not None:
            if last.tzinfo is not None:  # PostgreSQL returns aware datetimes
                last = last.astimezone(UTC).replace(tzinfo=None)
            days_since = max(0, (now_utc - last).days)
        items.append(
            DeadStockItem(
                product_id=row.product_id,
                name=row.name,
                category_name=row.category_name,
                image_path=row.image_path,
                stock_quantity=row.stock_quantity,
                tied_capital=row.tied_capital,
                last_sold_at=row.last_sold_at,
                days_since=days_since,
            )
        )
    return items


def category_breakdown(
    db: Session, store_id: UUID, date_from: datetime, date_to: datetime
) -> list[CategoryStat]:
    """Revenue/profit/quantity grouped by product category over the range.

    Uncategorised products fall into a single (category_id=None) bucket."""
    rows = db.execute(
        select(
            Product.category_id.label("category_id"),
            Category.name.label("name"),
            type_coerce(func.sum(SaleItem.line_total), Money()).label("revenue"),
            type_coerce(
                func.sum(
                    SaleItem.line_total
                    - Product.cost_price * SaleItem.quantity * SaleItem.unit_count
                ),
                Money(),
            ).label("profit"),
            func.sum(SaleItem.quantity * SaleItem.unit_count).label("quantity"),
        )
        .join(Sale, SaleItem.sale_id == Sale.id)
        .join(Product, SaleItem.product_id == Product.id)
        .outerjoin(Category, Product.category_id == Category.id)
        .where(_sale_items_in_range(store_id, date_from, date_to))
        .group_by(Product.category_id, Category.name)
        .order_by(desc("revenue"))
    ).all()
    return [CategoryStat.model_validate(row) for row in rows]


def sales_patterns(
    db: Session, store_id: UUID, date_from: datetime, date_to: datetime
) -> SalesPatterns:
    """When the shop is busy: revenue + sale count by store-local hour of day
    (0..23) and weekday (0=Monday). Bucketed in Python so it is timezone- and
    database-portable (no SQL date-part functions)."""
    rows = db.execute(
        select(Sale.created_at, Sale.total_amount).where(
            Sale.store_id == store_id,
            Sale.deleted_at.is_(None),
            Sale.created_at >= date_from,
            Sale.created_at <= date_to,
        )
    ).all()

    hourly = {h: [Decimal("0.00"), 0] for h in range(24)}
    weekday = {w: [Decimal("0.00"), 0] for w in range(7)}
    for created_at, total in rows:
        if created_at.tzinfo is not None:  # PostgreSQL returns aware datetimes
            created_at = created_at.astimezone(UTC).replace(tzinfo=None)
        local = from_utc_naive(created_at)
        amount = Decimal(str(total))
        hourly[local.hour][0] += amount
        hourly[local.hour][1] += 1
        weekday[local.weekday()][0] += amount
        weekday[local.weekday()][1] += 1

    return SalesPatterns(
        hourly=[
            HourBucket(hour=h, revenue=hourly[h][0], sales_count=hourly[h][1])
            for h in range(24)
        ],
        weekday=[
            WeekdayBucket(weekday=w, revenue=weekday[w][0], sales_count=weekday[w][1])
            for w in range(7)
        ],
    )


def customer_insights(
    db: Session, store_id: UUID, date_from: datetime, date_to: datetime
) -> CustomerInsights:
    """Active / new / returning customers over the range, plus guest sales.

    New = customers whose first-ever purchase falls inside the range."""
    active = (
        db.scalar(
            select(func.count(func.distinct(Sale.customer_id))).where(
                Sale.store_id == store_id,
                Sale.deleted_at.is_(None),
                Sale.customer_id.is_not(None),
                Sale.created_at >= date_from,
                Sale.created_at <= date_to,
            )
        )
        or 0
    )
    guest = (
        db.scalar(
            select(func.count())
            .select_from(Sale)
            .where(
                Sale.store_id == store_id,
                Sale.deleted_at.is_(None),
                Sale.customer_id.is_(None),
                Sale.created_at >= date_from,
                Sale.created_at <= date_to,
            )
        )
        or 0
    )
    first_sale = (
        select(
            Sale.customer_id.label("cid"),
            func.min(Sale.created_at).label("first_at"),
        )
        .where(
            Sale.store_id == store_id,
            Sale.deleted_at.is_(None),
            Sale.customer_id.is_not(None),
        )
        .group_by(Sale.customer_id)
        .subquery()
    )
    new = (
        db.scalar(
            select(func.count())
            .select_from(first_sale)
            .where(
                first_sale.c.first_at >= date_from,
                first_sale.c.first_at <= date_to,
            )
        )
        or 0
    )
    return CustomerInsights(
        active_customers=active,
        new_customers=new,
        returning_customers=max(0, active - new),
        guest_sales_count=guest,
    )


def financial_snapshot(db: Session, store_id: UUID) -> FinancialSnapshot:
    """Money owed to us (customer credit) and by us (supplier debt), now."""
    customer = db.execute(
        select(
            type_coerce(
                func.coalesce(func.sum(Sale.total_amount - Sale.paid_amount), 0),
                Money(),
            ).label("total"),
            func.count().label("count"),
        ).where(
            Sale.store_id == store_id,
            Sale.deleted_at.is_(None),
            Sale.paid_amount < Sale.total_amount,
        )
    ).one()
    supplier = db.execute(
        select(
            type_coerce(
                func.coalesce(
                    func.sum(PurchaseOrder.total_amount - PurchaseOrder.paid_amount), 0
                ),
                Money(),
            ).label("total"),
            func.count().label("count"),
        ).where(
            PurchaseOrder.store_id == store_id,
            PurchaseOrder.deleted_at.is_(None),
            PurchaseOrder.paid_amount < PurchaseOrder.total_amount,
        )
    ).one()
    return FinancialSnapshot(
        customer_credit_total=customer.total,
        customer_credit_count=customer.count,
        supplier_debt_total=supplier.total,
        supplier_debt_count=supplier.count,
    )
