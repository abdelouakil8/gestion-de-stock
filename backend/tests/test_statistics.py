"""Statistics service: exact revenue/profit, date ranges, top products,
plus Phase 6 per-product period stats and the calendar overview.

Sales are pinned to deterministic timestamps; local→UTC conversion goes
through statistics.to_utc_naive so the tests hold in any machine timezone.
"""

from datetime import datetime, timedelta
from decimal import Decimal

from app.schemas.category import CategoryCreate
from app.schemas.customer import CustomerCreate
from app.schemas.product import ProductCreate
from app.schemas.sale import CartItem, CheckoutRequest, PaymentInfo
from app.schemas.store import StoreCreate
from app.schemas.supplier import (
    PurchaseOrderCreate,
    PurchaseOrderItemCreate,
    SupplierCreate,
)
from app.services import (
    categories,
    customers,
    products,
    purchasing,
    sales,
    statistics,
    stores,
    suppliers,
)
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


# ------------------------------------ Phase 12: dashboard analytics


def make_priced(db, store, name, cost, detail, stock=1000, category_id=None):
    """Product with an explicit détail price (retail-value tests) and an
    optional category."""
    return products.create_product(
        db,
        ProductCreate(
            store_id=store.id,
            name=name,
            cost_price=Decimal(cost),
            price_detail=Decimal(detail),
            price_gros=Decimal(detail),
            price_super_gros=Decimal("0.01"),
            stock_quantity=stock,
            category_id=category_id,
        ),
    )


def sell_for(db, store, product, quantity, price, created_at, customer_id=None):
    """Finalize a sale (full payment), optionally attached to a customer."""
    payment = (
        PaymentInfo(mode="full", customer_id=customer_id)
        if customer_id is not None
        else PaymentInfo()
    )
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
            payment=payment,
        ),
    )
    sale.created_at = created_at
    db.commit()
    return sale


def test_top_products_sort_by_profit(db):
    store = stores.create_store(db, StoreCreate(name="Boutique Profit"))
    a = make_product(db, store, "Produit A", "10.00", "12.00")
    b = make_product(db, store, "Produit B", "10.00", "12.00")
    c = make_product(db, store, "Produit C", "10.00", "12.00")

    sell(db, store, a, 5, "15.00", JAN_15)  # qty 5,  profit (15-10)*5 = 25
    sell(db, store, b, 20, "12.00", JAN_15)  # qty 20, profit (12-10)*20 = 40
    sell(db, store, c, 3, "30.00", JAN_15)  # qty 3,  profit (30-10)*3 = 60

    by_qty = statistics.top_products(db, store.id, *JAN_RANGE)
    assert [t.name for t in by_qty] == ["Produit B", "Produit A", "Produit C"]
    assert by_qty[0].profit == Decimal("40.00")  # profit now populated

    by_profit = statistics.top_products(db, store.id, *JAN_RANGE, sort="profit")
    assert [t.name for t in by_profit] == ["Produit C", "Produit B", "Produit A"]
    assert by_profit[0].profit == Decimal("60.00")
    assert by_profit[0].revenue == Decimal("90.00")


def test_daily_evolution_zero_fills_gaps(db):
    store = stores.create_store(db, StoreCreate(name="Boutique Évolution"))
    water = make_product(db, store, "Eau", "25.00", "30.00")

    sell(db, store, water, 3, "40.00", datetime(2026, 1, 1, 12, 0))  # rev 120 pr 45
    sell(db, store, water, 2, "40.00", datetime(2026, 1, 3, 12, 0))  # rev 80  pr 30

    points = statistics.daily_evolution(
        db, store.id, datetime(2026, 1, 1, 0, 0), datetime(2026, 1, 3, 23, 59, 59)
    )
    assert [p.day.isoformat() for p in points] == [
        "2026-01-01",
        "2026-01-02",
        "2026-01-03",
    ]
    assert [p.revenue for p in points] == [
        Decimal("120.00"),
        Decimal("0.00"),
        Decimal("80.00"),
    ]
    assert [p.profit for p in points] == [
        Decimal("45.00"),
        Decimal("0.00"),
        Decimal("30.00"),
    ]


def test_inventory_stats_value_and_health(db):
    store = stores.create_store(db, StoreCreate(name="Boutique Stock"))
    make_priced(db, store, "Plein", "25.00", "40.00", stock=10)  # cost 250 retail 400
    make_priced(db, store, "Bas", "10.00", "15.00", stock=2)  # low: 0<2<=5
    make_priced(db, store, "Rupture", "100.00", "150.00", stock=0)  # out of stock

    inv = statistics.inventory_stats(db, store.id)
    assert inv.stock_value_cost == Decimal("270.00")  # 250 + 20 + 0
    assert inv.stock_value_retail == Decimal("430.00")  # 400 + 30 + 0
    assert inv.product_count == 3
    assert inv.active_count == 3
    assert inv.out_of_stock_count == 1
    assert inv.low_stock_count == 1


def test_dead_stock_ranks_by_tied_capital_and_excludes_recent(db):
    store = stores.create_store(db, StoreCreate(name="Boutique Dormante"))
    old = make_priced(db, store, "Ancien", "50.00", "60.00", stock=10)
    make_priced(db, store, "Jamais", "20.00", "25.00", stock=5)  # never sold
    fresh = make_priced(db, store, "Frais", "10.00", "12.00", stock=8)
    empty = make_priced(db, store, "Rupture", "30.00", "35.00", stock=1)

    sell_local(db, store, old, 1, "60.00", NOW_LOCAL - timedelta(days=100))  # stock 9
    sell_local(db, store, fresh, 1, "12.00", NOW_LOCAL)  # sold today
    sell_local(db, store, empty, 1, "35.00", NOW_LOCAL - timedelta(days=200))  # stock 0

    items = statistics.dead_stock(db, store.id, days=60, now=NOW_LOCAL)
    assert [i.name for i in items] == ["Ancien", "Jamais"]  # fresh + empty excluded
    assert items[0].tied_capital == Decimal("450.00")  # 50 * 9
    assert items[0].days_since is not None and items[0].days_since >= 60
    assert items[1].tied_capital == Decimal("100.00")  # 20 * 5
    assert items[1].days_since is None  # never sold


def test_category_breakdown_groups_and_buckets_uncategorised(db):
    store = stores.create_store(db, StoreCreate(name="Boutique Catégories"))
    drinks = categories.create_category(
        db, CategoryCreate(store_id=store.id, name="Boissons")
    )
    water = make_priced(db, store, "Eau", "25.00", "40.00", category_id=drinks.id)
    juice = make_priced(db, store, "Jus", "80.00", "95.00", category_id=drinks.id)
    misc = make_priced(db, store, "Divers", "10.00", "12.00")  # no category

    sell(db, store, water, 3, "40.00", JAN_15)  # rev 120 pr 45 qty 3
    sell(db, store, juice, 2, "95.00", JAN_15)  # rev 190 pr 30 qty 2
    sell(db, store, misc, 5, "12.00", JAN_15)  # rev 60  pr 10 qty 5

    cats = statistics.category_breakdown(db, store.id, *JAN_RANGE)
    assert [c.name for c in cats] == ["Boissons", None]  # ordered by revenue
    assert cats[0].revenue == Decimal("310.00")
    assert cats[0].profit == Decimal("75.00")
    assert cats[0].quantity == 5
    assert cats[1].category_id is None
    assert cats[1].revenue == Decimal("60.00")


def test_sales_patterns_bucket_by_local_hour_and_weekday(db):
    store = stores.create_store(db, StoreCreate(name="Boutique Rythme"))
    water = make_product(db, store, "Eau", "25.00", "30.00")

    monday_10h = datetime(2026, 6, 15, 10, 0)  # Monday = weekday 0
    wednesday_15h = datetime(2026, 6, 17, 15, 0)  # Wednesday = weekday 2
    sell_local(db, store, water, 1, "40.00", monday_10h)
    sell_local(db, store, water, 1, "40.00", monday_10h)
    sell_local(db, store, water, 1, "40.00", wednesday_15h)

    patterns = statistics.sales_patterns(
        db, store.id, datetime(2026, 6, 1), datetime(2026, 6, 30, 23, 59, 59)
    )
    hourly = {h.hour: h for h in patterns.hourly}
    weekday = {w.weekday: w for w in patterns.weekday}
    assert len(patterns.hourly) == 24 and len(patterns.weekday) == 7
    assert hourly[10].sales_count == 2 and hourly[10].revenue == Decimal("80.00")
    assert hourly[15].sales_count == 1 and hourly[15].revenue == Decimal("40.00")
    assert weekday[0].sales_count == 2  # Monday
    assert weekday[2].sales_count == 1  # Wednesday


def test_customer_insights_active_new_returning_guest(db):
    store = stores.create_store(db, StoreCreate(name="Boutique Clients"))
    water = make_product(db, store, "Eau", "25.00", "30.00", stock=1000)
    alice = customers.create_customer(
        db, CustomerCreate(store_id=store.id, name="Alice", phone="0550000001")
    )
    bob = customers.create_customer(
        db, CustomerCreate(store_id=store.id, name="Bob", phone="0550000002")
    )

    feb_from = datetime(2026, 2, 1)
    feb_to = datetime(2026, 2, 28, 23, 59, 59)

    # Alice: first-ever purchase inside the range -> new + active.
    sell_for(db, store, water, 1, "40.00", datetime(2026, 2, 10, 10, 0), alice.id)
    # Bob: first purchase BEFORE the range, then again inside -> returning.
    sell_for(db, store, water, 1, "40.00", datetime(2026, 1, 5, 10, 0), bob.id)
    sell_for(db, store, water, 1, "40.00", datetime(2026, 2, 15, 10, 0), bob.id)
    # A walk-in (guest) sale inside the range.
    sell(db, store, water, 1, "40.00", datetime(2026, 2, 20, 10, 0))

    insights = statistics.customer_insights(db, store.id, feb_from, feb_to)
    assert insights.active_customers == 2  # Alice + Bob
    assert insights.new_customers == 1  # Alice
    assert insights.returning_customers == 1  # Bob
    assert insights.guest_sales_count == 1


def test_financial_snapshot_customer_credit_and_supplier_debt(db):
    store = stores.create_store(db, StoreCreate(name="Boutique Finances"))
    water = make_product(db, store, "Eau", "25.00", "30.00", stock=1000)
    customer = customers.create_customer(
        db, CustomerCreate(store_id=store.id, name="Débiteur", phone="0550000009")
    )

    # A credit sale: total 120, paid 50 -> 70 owed to us.
    sales.finalize_sale(
        db,
        CheckoutRequest(
            store_id=store.id,
            items=[
                CartItem(
                    product_id=water.id,
                    quantity=3,
                    unit_price_override=Decimal("40.00"),
                )
            ],
            payment=PaymentInfo(
                mode="partial", amount_paid=Decimal("50.00"), customer_id=customer.id
            ),
        ),
    )
    # A fully paid sale never counts as credit.
    sell(db, store, water, 1, "40.00", JAN_15)

    # A purchase order: total 200, paid 50 -> 150 we owe the supplier.
    supplier = suppliers.create_supplier(
        db, SupplierCreate(store_id=store.id, name="Grossiste", phone="0660000000")
    )
    purchasing.receive_stock(
        db,
        PurchaseOrderCreate(
            store_id=store.id,
            supplier_id=supplier.id,
            items=[
                PurchaseOrderItemCreate(
                    product_id=water.id, quantity=1, unit_cost=Decimal("200.00")
                )
            ],
            payment_amount=Decimal("50.00"),
        ),
    )

    snap = statistics.financial_snapshot(db, store.id)
    assert snap.customer_credit_total == Decimal("70.00")
    assert snap.customer_credit_count == 1
    assert snap.supplier_debt_total == Decimal("150.00")
    assert snap.supplier_debt_count == 1
