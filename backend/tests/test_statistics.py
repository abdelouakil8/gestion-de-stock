"""Statistics service: exact revenue/profit, date ranges, top products,
plus Phase 6 per-product period stats and the calendar overview.

Sales are pinned to deterministic timestamps; local→UTC conversion goes
through statistics.to_utc_naive so the tests hold in any machine timezone.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from app.schemas.product import ProductCreate
from app.schemas.sale import CartItem, CheckoutRequest
from app.schemas.store import StoreCreate
from app.services import products, sales, statistics, stores
from app.services.statistics import to_utc_naive

JAN_15 = datetime(2026, 1, 15, 12, 0)
FEB_15 = datetime(2026, 2, 15, 12, 0)
JAN_RANGE = (datetime(2026, 1, 1), datetime(2026, 1, 31, 23, 59, 59))
YEAR_RANGE = (datetime(2026, 1, 1), datetime(2026, 12, 31, 23, 59, 59))


def make_product(db, store, name, cost, floor, stock=1000):
    return products.create_product(
        db,
        ProductCreate(
            store_id=store.id,
            name=name,
            cost_price=Decimal(cost),
            price_detail=Decimal("999.00"),  # overrides drive test prices
            price_gros=Decimal("999.00"),
            price_super_gros=Decimal(floor),
            stock_quantity=stock,
        ),
    )


def sell(db, store, product, quantity, price, created_at):
    sale = sales.finalize_sale(
        db,
        CheckoutRequest(
            store_id=store.id,
            items=[
                CartItem(
                    product_id=product.id,
                    quantity=quantity,
                    unit_price_override=Decimal(price),
                )
            ],
        ),
    )
    sale.created_at = created_at  # deterministic date for range tests
    db.commit()
    return sale


def test_summary_revenue_profit_and_range_filtering(db):
    store = stores.create_store(db, StoreCreate(name="Boutique Stats"))
    water = make_product(db, store, "Eau", "25.00", "30.00")
    juice = make_product(db, store, "Jus", "80.00", "95.00")

    sell(db, store, water, 3, "40.00", JAN_15)  # revenue 120.00, profit 45.00
    sell(db, store, juice, 2, "95.00", JAN_15)  # revenue 190.00, profit 30.00
    sell(db, store, water, 10, "35.00", FEB_15)  # revenue 350.00, profit 100.00

    january = statistics.sales_summary(db, store.id, *JAN_RANGE)
    assert january.revenue == Decimal("310.00")
    assert january.gross_profit == Decimal("75.00")
    assert january.sales_count == 2

    year = statistics.sales_summary(db, store.id, *YEAR_RANGE)
    assert year.revenue == Decimal("660.00")
    assert year.gross_profit == Decimal("175.00")
    assert year.sales_count == 3


def test_summary_empty_range_is_zero_not_error(db):
    store = stores.create_store(db, StoreCreate(name="Boutique Vide"))
    result = statistics.sales_summary(db, store.id, *JAN_RANGE)
    assert result.revenue == Decimal("0.00")
    assert result.gross_profit == Decimal("0.00")
    assert result.sales_count == 0


def test_soft_deleted_sale_excluded_from_statistics(db):
    store = stores.create_store(db, StoreCreate(name="Boutique Annul"))
    water = make_product(db, store, "Eau", "25.00", "30.00")
    kept = sell(db, store, water, 2, "40.00", JAN_15)
    cancelled = sell(db, store, water, 5, "40.00", JAN_15)
    sales.soft_delete_sale(db, cancelled.id)

    january = statistics.sales_summary(db, store.id, *JAN_RANGE)
    assert january.revenue == kept.total_amount == Decimal("80.00")
    assert january.sales_count == 1


def test_top_products_ordering_and_limit(db):
    store = stores.create_store(db, StoreCreate(name="Boutique Top"))
    a = make_product(db, store, "Produit A", "10.00", "12.00")
    b = make_product(db, store, "Produit B", "10.00", "12.00")
    c = make_product(db, store, "Produit C", "10.00", "12.00")

    sell(db, store, a, 5, "15.00", JAN_15)
    sell(db, store, b, 20, "15.00", JAN_15)
    sell(db, store, c, 9, "15.00", JAN_15)

    top = statistics.top_products(db, store.id, *JAN_RANGE)
    assert [t.name for t in top] == ["Produit B", "Produit C", "Produit A"]
    assert top[0].quantity_sold == 20
    assert top[0].revenue == Decimal("300.00")

    top2 = statistics.top_products(db, store.id, *JAN_RANGE, limit=2)
    assert [t.name for t in top2] == ["Produit B", "Produit C"]


def test_statistics_are_store_scoped(db):
    store1 = stores.create_store(db, StoreCreate(name="Boutique 1"))
    store2 = stores.create_store(db, StoreCreate(name="Boutique 2"))
    p1 = make_product(db, store1, "Eau", "25.00", "30.00")
    sell(db, store1, p1, 1, "40.00", JAN_15)

    assert statistics.sales_summary(db, store2.id, *JAN_RANGE).revenue == Decimal(
        "0.00"
    )
    assert statistics.top_products(db, store2.id, *JAN_RANGE) == []


# ------------------------------------------ Phase 6: per-product periods


NOW_LOCAL = datetime(2026, 6, 17, 15, 0)  # Wednesday


def sell_local(db, store, product, quantity, price, local_dt):
    """Sell with created_at pinned via the same local→UTC conversion the
    statistics service uses, so period bucketing is timezone-proof."""
    return sell(db, store, product, quantity, price, to_utc_naive(local_dt))


def test_product_stats_windows(db):
    store = stores.create_store(db, StoreCreate(name="Boutique Périodes"))
    product = make_product(db, store, "Eau", "25.00", "30.00")
    other = make_product(db, store, "Jus", "10.00", "12.00")

    sell_local(db, store, product, 2, "40.00", NOW_LOCAL.replace(hour=10))
    sell_local(db, store, product, 3, "40.00", NOW_LOCAL - timedelta(days=3))
    sell_local(db, store, product, 5, "40.00", NOW_LOCAL - timedelta(days=20))
    sell_local(db, store, product, 7, "40.00", NOW_LOCAL - timedelta(days=200))
    sell_local(db, store, product, 11, "40.00", NOW_LOCAL - timedelta(days=400))
    # Noise from another product never leaks in.
    sell_local(db, store, other, 50, "12.00", NOW_LOCAL.replace(hour=9))

    stats = statistics.product_stats(db, store.id, product.id, now=NOW_LOCAL)
    by_period = {p.period: p for p in stats.periods}
    assert set(by_period) == {
        "today",
        "last_7_days",
        "last_30_days",
        "last_365_days",
        "all_time",
    }

    assert by_period["today"].units_sold == 2
    assert by_period["last_7_days"].units_sold == 5
    assert by_period["last_30_days"].units_sold == 10
    assert by_period["last_365_days"].units_sold == 17
    assert by_period["all_time"].units_sold == 28

    # Exact integer-cent aggregation: revenue = units × 40, profit = units × 15.
    assert by_period["last_30_days"].revenue == Decimal("400.00")
    assert by_period["last_30_days"].profit == Decimal("150.00")
    assert by_period["all_time"].revenue == Decimal("1120.00")
    assert by_period["all_time"].profit == Decimal("420.00")


def test_product_stats_excludes_soft_deleted_and_unknown_product(db):
    store = stores.create_store(db, StoreCreate(name="Boutique Périodes 2"))
    product = make_product(db, store, "Eau", "25.00", "30.00")
    kept = sell_local(db, store, product, 2, "40.00", NOW_LOCAL.replace(hour=10))
    cancelled = sell_local(db, store, product, 9, "40.00", NOW_LOCAL.replace(hour=11))
    sales.soft_delete_sale(db, cancelled.id)
    assert kept is not None

    stats = statistics.product_stats(db, store.id, product.id, now=NOW_LOCAL)
    today = next(p for p in stats.periods if p.period == "today")
    assert today.units_sold == 2

    from uuid import uuid4

    assert statistics.product_stats(db, store.id, uuid4(), now=NOW_LOCAL) is None


# ------------------------------------------------ Phase 6: overview


def test_overview_calendar_periods_with_previous_comparison(db):
    store = stores.create_store(db, StoreCreate(name="Boutique Vue"))
    product = make_product(db, store, "Eau", "25.00", "30.00")

    # One sale in each bucket; amounts distinct so sums identify sources.
    sell_local(db, store, product, 1, "40.00", NOW_LOCAL.replace(hour=10))  # today
    sell_local(
        db, store, product, 1, "41.00", NOW_LOCAL - timedelta(days=1)
    )  # Tue (this week)
    sell_local(
        db, store, product, 1, "42.00", NOW_LOCAL - timedelta(days=7)
    )  # last week
    sell_local(
        db, store, product, 1, "43.00", datetime(2026, 5, 20, 12, 0)
    )  # last month
    sell_local(db, store, product, 1, "44.00", datetime(2025, 8, 1, 12, 0))  # last year

    result = statistics.overview(db, store.id, now=NOW_LOCAL)
    by_period = {p.period: p for p in result.periods}
    assert set(by_period) == {"today", "this_week", "this_month", "this_year"}

    today = by_period["today"]
    assert today.current.revenue == Decimal("40.00")
    assert today.current.sales_count == 1
    assert today.previous.revenue == Decimal("41.00")  # yesterday

    week = by_period["this_week"]  # Mon 15 → Wed 17: today + yesterday
    assert week.current.revenue == Decimal("81.00")
    assert week.current.sales_count == 2
    assert week.previous.revenue == Decimal("42.00")  # last week

    month = by_period["this_month"]  # June: 10th, 16th, 17th
    assert month.current.revenue == Decimal("123.00")
    assert month.current.sales_count == 3
    assert month.previous.revenue == Decimal("43.00")  # May

    year = by_period["this_year"]
    assert year.current.revenue == Decimal("166.00")
    assert year.current.sales_count == 4
    assert year.previous.revenue == Decimal("44.00")  # 2025
    # Profit stays exact through every aggregation (cost 25.00 each).
    assert year.current.gross_profit == Decimal("66.00")  # 15+16+17+18
