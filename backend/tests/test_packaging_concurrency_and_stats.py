"""Packaging concurrency (stock deducted by quantity*unit_count, atomically)
and statistics/profit on base units (backward compatible with unit_count=1).
"""

from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import InsufficientStockError
from app.models import Base, Product, SaleItem
from app.schemas.product import PackagingCreate, ProductCreate
from app.schemas.sale import CartItem, CheckoutRequest, PaymentInfo
from app.schemas.store import StoreCreate
from app.services import customers, products, sales, statistics, stores
from app.schemas.customer import CustomerCreate


def _carton(unit_count=24, detail="2100.00", gros="2050.00", super_gros="2000.00"):
    return PackagingCreate(
        label="Carton",
        unit_count=unit_count,
        price_detail=Decimal(detail),
        price_gros=Decimal(gros),
        price_super_gros=Decimal(super_gros),
    )


def _make(db, *, stock, packagings=None):
    store = stores.create_store(db, StoreCreate(name="B"))
    product = products.create_product(
        db,
        ProductCreate(
            store_id=store.id,
            name="dikor",
            cost_price=Decimal("10.00"),
            price_detail=Decimal("100.00"),
            price_gros=Decimal("100.00"),
            price_super_gros=Decimal("100.00"),
            stock_quantity=stock,
            packagings=packagings,
        ),
    )
    return store, product


# ------------------------------------------------------------- concurrency


def test_two_cartons_compete_for_exact_stock(tmp_path):
    """Stock = 24 = exactly one carton (unit_count 24). Two concurrent
    carton checkouts: exactly one wins, stock never negative."""
    engine = create_engine(f"sqlite:///{tmp_path / 'pk.db'}")
    Base.metadata.create_all(engine)
    Factory = sessionmaker(bind=engine, autoflush=False)

    with Session(engine) as setup:
        store, product = _make(setup, stock=24, packagings=[_carton(unit_count=24)])
        store_id, product_id, carton_id = store.id, product.id, product.packagings[0].id

    s1, s2 = Factory(), Factory()
    try:
        line = {"product_id": product_id, "quantity": 1, "packaging_id": carton_id}
        sales.finalize_sale(
            s1, CheckoutRequest(store_id=store_id, items=[CartItem(**line)])
        )
        with pytest.raises(InsufficientStockError):
            sales.finalize_sale(
                s2, CheckoutRequest(store_id=store_id, items=[CartItem(**line)])
            )
        with Session(engine) as check:
            final = check.scalar(select(Product).where(Product.id == product_id))
            assert final.stock_quantity == 0
    finally:
        s1.close()
        s2.close()


def test_carton_and_units_cannot_oversell(tmp_path):
    """Stock 25. One buys a carton (24), one buys 2 units (=26 > 25).
    They cannot both fully succeed; stock never goes negative."""
    engine = create_engine(f"sqlite:///{tmp_path / 'pk2.db'}")
    Base.metadata.create_all(engine)
    Factory = sessionmaker(bind=engine, autoflush=False)

    with Session(engine) as setup:
        store, product = _make(setup, stock=25, packagings=[_carton(unit_count=24)])
        store_id, product_id, carton_id = store.id, product.id, product.packagings[0].id

    s1, s2 = Factory(), Factory()
    outcomes = []
    for sess, line in (
        (s1, {"product_id": product_id, "quantity": 1, "packaging_id": carton_id}),
        (s2, {"product_id": product_id, "quantity": 2}),
    ):
        try:
            sales.finalize_sale(
                sess, CheckoutRequest(store_id=store_id, items=[CartItem(**line)])
            )
            outcomes.append("ok")
        except InsufficientStockError:
            outcomes.append("rejected")
    s1.close()
    s2.close()

    with Session(engine) as check:
        final = check.scalar(select(Product).where(Product.id == product_id))
        assert final.stock_quantity >= 0
        # The carton (24) succeeds first, leaving 1 — the 2-unit line must fail.
        assert outcomes == ["ok", "rejected"]
        assert final.stock_quantity == 1


# --------------------------------------------------------------- statistics


def test_stats_backward_compatible_without_packaging(db):
    """A product sold only as base units yields the classic numbers."""
    store, product = _make(db, stock=100)
    sales.finalize_sale(
        db,
        CheckoutRequest(
            store_id=store.id,
            items=[CartItem(product_id=product.id, quantity=5)],  # 5 @ 100
        ),
    )
    stats = statistics.product_stats(db, store.id, product.id)
    all_time = next(p for p in stats.periods if p.period == "all_time")
    assert all_time.units_sold == 5
    assert all_time.revenue == Decimal("500.00")
    assert all_time.profit == Decimal("450.00")  # (100-10)*5


def test_stats_base_units_with_cartons(db):
    store, product = _make(db, stock=200, packagings=[_carton(unit_count=24)])
    carton = product.packagings[0]
    sales.finalize_sale(
        db,
        CheckoutRequest(
            store_id=store.id,
            items=[
                CartItem(product_id=product.id, quantity=2, packaging_id=carton.id)
            ],
        ),
    )
    stats = statistics.product_stats(db, store.id, product.id)
    all_time = next(p for p in stats.periods if p.period == "all_time")
    assert all_time.units_sold == 48  # 2 cartons * 24 base units
    assert all_time.revenue == Decimal("4200.00")  # 2100 * 2 (package price)
    # profit = revenue - cost*base_units = 4200 - 10*48
    assert all_time.profit == Decimal("3720.00")


def test_customer_profit_uses_base_units(db):
    store, product = _make(db, stock=200, packagings=[_carton(unit_count=24)])
    carton = product.packagings[0]
    customer = customers.create_customer(
        db, CustomerCreate(store_id=store.id, name="Ali", phone="0555000000")
    )
    sales.finalize_sale(
        db,
        CheckoutRequest(
            store_id=store.id,
            items=[CartItem(product_id=product.id, quantity=1, packaging_id=carton.id)],
            payment=PaymentInfo(
                mode="partial", amount_paid=Decimal("100.00"), customer_id=customer.id
            ),
        ),
    )
    stats = customers.customer_stats(db, customer.id)
    # revenue billed = 2100; profit = 2100 - 10*24 = 1860
    assert stats.total_revenue == Decimal("2100.00")
    assert stats.total_profit == Decimal("1860.00")


def test_money_exact_no_float_drift_with_cartons(db):
    store, product = _make(
        db, stock=500, packagings=[_carton(unit_count=7, detail="12.33", gros="12.00", super_gros="11.00")]
    )
    carton = product.packagings[0]
    sale = sales.finalize_sale(
        db,
        CheckoutRequest(
            store_id=store.id,
            items=[CartItem(product_id=product.id, quantity=3, packaging_id=carton.id)],
        ),
    )
    assert sale.items[0].line_total == Decimal("36.99")  # 12.33 * 3
    line_sum = sum((i.line_total for i in sale.items), Decimal("0"))
    assert line_sum == sale.total_amount
