"""Business rules: named price levels, price floor, atomic stock, checkout.

Phase 6 adaptation: quantity-tier resolution is superseded by named price
levels (detail / gros / super_gros) — the floor is now price_super_gros.
Covers: level ordering validation, server-side resolution per level, floor
at/below boundary, zero/negative quantities, stock to exactly zero vs
below, Decimal exactness on awkward totals, atomicity (nothing partially
committed), and the closed check-then-write race.
"""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.exceptions import (
    InsufficientStockError,
    InvalidPriceLevelsError,
    InvalidQuantityError,
    PriceBelowFloorError,
    ProductUnavailableError,
)
from app.models import Base, Product, Sale, SaleItem
from app.schemas.category import CategoryCreate
from app.schemas.product import ProductCreate, ProductUpdate
from app.schemas.sale import CartItem, CheckoutRequest
from app.schemas.store import StoreCreate
from app.services import categories, pricing, products, sales, stores


def build_product(db, *, stock=100, detail="40.00", gros="37.50", super_gros="30.00"):
    store = stores.create_store(db, StoreCreate(name="Boutique Test"))
    category = categories.create_category(
        db, CategoryCreate(store_id=store.id, name="Boissons")
    )
    product = products.create_product(
        db,
        ProductCreate(
            store_id=store.id,
            category_id=category.id,
            name="Eau minérale 1.5L",
            barcode="6130000000015",
            cost_price=Decimal("25.00"),
            price_detail=Decimal(detail),
            price_gros=Decimal(gros),
            price_super_gros=Decimal(super_gros),
            stock_quantity=stock,
        ),
    )
    return store, product


def checkout(db, store, lines) -> Sale:
    return sales.finalize_sale(
        db,
        CheckoutRequest(
            store_id=store.id,
            items=[CartItem(**line) for line in lines],
        ),
    )


# ---------------------------------------------------------------- pricing


def test_price_level_resolution(db):
    _, product = build_product(db)
    assert pricing.resolve_unit_price(product, "detail") == Decimal("40.00")
    assert pricing.resolve_unit_price(product, "gros") == Decimal("37.50")
    assert pricing.resolve_unit_price(product, "super_gros") == Decimal("30.00")
    # Default level is detail.
    assert pricing.resolve_unit_price(product) == Decimal("40.00")


def test_price_level_ordering_validated_at_creation(db):
    store = stores.create_store(db, StoreCreate(name="B"))
    with pytest.raises(InvalidPriceLevelsError):
        products.create_product(
            db,
            ProductCreate(
                store_id=store.id,
                name="Produit incohérent",
                cost_price=Decimal("10.00"),
                price_detail=Decimal("20.00"),
                price_gros=Decimal("25.00"),  # gros > detail: rejected
                price_super_gros=Decimal("15.00"),
            ),
        )
    with pytest.raises(InvalidPriceLevelsError):
        products.create_product(
            db,
            ProductCreate(
                store_id=store.id,
                name="Produit incohérent 2",
                cost_price=Decimal("10.00"),
                price_detail=Decimal("20.00"),
                price_gros=Decimal("18.00"),
                price_super_gros=Decimal("19.00"),  # super_gros > gros: rejected
            ),
        )
    # Equal prices on all levels are legal (detail >= gros >= super_gros).
    product = products.create_product(
        db,
        ProductCreate(
            store_id=store.id,
            name="Produit prix unique",
            cost_price=Decimal("10.00"),
            price_detail=Decimal("20.00"),
            price_gros=Decimal("20.00"),
            price_super_gros=Decimal("20.00"),
        ),
    )
    assert product.price_detail == Decimal("20.00")


def test_price_level_ordering_validated_on_partial_update(db):
    _, product = build_product(db)  # 40 / 37.50 / 30
    with pytest.raises(InvalidPriceLevelsError):
        # Raising the floor above gros must be rejected even though the
        # request itself only touches one field.
        products.update_product(
            db, product.id, ProductUpdate(price_super_gros=Decimal("38.00"))
        )
    db.rollback()
    updated = products.update_product(
        db, product.id, ProductUpdate(price_super_gros=Decimal("35.00"))
    )
    assert updated.price_super_gros == Decimal("35.00")


def test_zero_and_negative_quantity_rejected(db):
    _, product = build_product(db)
    with pytest.raises(InvalidQuantityError):
        pricing.resolve_unit_price(product, "detail", 0)
    with pytest.raises(InvalidQuantityError):
        pricing.resolve_unit_price(product, "detail", -3)


def test_price_floor_is_super_gros_equal_allowed_below_rejected(db):
    _, product = build_product(db)
    pricing.validate_price_floor(product, Decimal("30.00"))  # at floor: OK
    with pytest.raises(PriceBelowFloorError) as exc:
        pricing.validate_price_floor(product, Decimal("29.99"))
    assert exc.value.code == "price_below_floor"
    assert "prix minimum" in str(exc.value.message).lower()


def test_db_check_constraint_backstops_price_ordering(db):
    _, product = build_product(db)
    with pytest.raises(IntegrityError):
        db.execute(
            update(Product)
            .where(Product.id == product.id)
            .values(price_gros=Decimal("45.00"))  # above detail: DB says no
        )
    db.rollback()


# ---------------------------------------------------------------- checkout


def test_checkout_resolves_price_server_side_per_level(db):
    store, product = build_product(db, stock=50)
    sale = checkout(
        db, store, [{"product_id": product.id, "quantity": 6, "price_level": "gros"}]
    )
    assert sale.total_amount == Decimal("225.00")  # 6 x 37.50
    assert sale.items[0].unit_price_applied == Decimal("37.50")
    assert sale.items[0].price_level == "gros"  # persisted on the line
    db.refresh(product)
    assert product.stock_quantity == 44


def test_checkout_default_level_is_detail(db):
    store, product = build_product(db, stock=10)
    sale = checkout(db, store, [{"product_id": product.id, "quantity": 2}])
    assert sale.items[0].price_level == "detail"
    assert sale.items[0].unit_price_applied == Decimal("40.00")
    assert sale.total_amount == Decimal("80.00")


def test_checkout_at_super_gros_level_is_legal(db):
    """Selling at the floor level itself is always allowed."""
    store, product = build_product(db, stock=10)
    sale = checkout(
        db,
        store,
        [{"product_id": product.id, "quantity": 1, "price_level": "super_gros"}],
    )
    assert sale.items[0].unit_price_applied == Decimal("30.00")


def test_checkout_to_exactly_zero_stock_allowed(db):
    store, product = build_product(db, stock=6)
    checkout(db, store, [{"product_id": product.id, "quantity": 6}])
    db.refresh(product)
    assert product.stock_quantity == 0


def test_checkout_below_zero_stock_rejected(db):
    store, product = build_product(db, stock=5)
    with pytest.raises(InsufficientStockError):
        checkout(db, store, [{"product_id": product.id, "quantity": 6}])
    db.refresh(product)
    assert product.stock_quantity == 5  # untouched


def test_override_at_floor_allowed_below_floor_rejected(db):
    store, product = build_product(db, stock=10)
    sale = checkout(
        db,
        store,
        [
            {
                "product_id": product.id,
                "quantity": 1,
                "unit_price_override": Decimal("30.00"),
            }
        ],
    )
    assert sale.items[0].unit_price_applied == Decimal("30.00")

    with pytest.raises(PriceBelowFloorError):
        checkout(
            db,
            store,
            [
                {
                    "product_id": product.id,
                    "quantity": 1,
                    "unit_price_override": Decimal("29.99"),
                }
            ],
        )


def test_failed_line_rolls_back_entire_sale(db):
    store, p1 = build_product(db, stock=50)
    p2 = products.create_product(
        db,
        ProductCreate(
            store_id=store.id,
            name="Produit épuisé",
            cost_price=Decimal("10.00"),
            price_detail=Decimal("15.00"),
            price_gros=Decimal("13.00"),
            price_super_gros=Decimal("12.00"),
            stock_quantity=1,
        ),
    )
    with pytest.raises(InsufficientStockError):
        checkout(
            db,
            store,
            [
                {"product_id": p1.id, "quantity": 10},  # valid line
                {"product_id": p2.id, "quantity": 5},  # fails
            ],
        )
    db.refresh(p1)
    db.refresh(p2)
    assert p1.stock_quantity == 50  # first line fully rolled back
    assert p2.stock_quantity == 1
    assert db.scalar(select(Sale)) is None
    assert db.scalar(select(SaleItem)) is None


def test_archived_or_inactive_product_rejected(db):
    store, product = build_product(db)
    products.soft_delete_product(db, product.id)
    with pytest.raises(ProductUnavailableError):
        checkout(db, store, [{"product_id": product.id, "quantity": 1}])

    _, p_inactive = build_product(db)
    p_inactive.is_active = False
    db.commit()
    with pytest.raises(ProductUnavailableError):
        checkout(db, store, [{"product_id": p_inactive.id, "quantity": 1}])


def test_unknown_product_and_wrong_store_rejected(db):
    store, product = build_product(db)
    other_store = stores.create_store(db, StoreCreate(name="Autre boutique"))
    with pytest.raises(ProductUnavailableError):
        checkout(db, store, [{"product_id": uuid4(), "quantity": 1}])
    with pytest.raises(ProductUnavailableError):
        checkout(db, other_store, [{"product_id": product.id, "quantity": 1}])


def test_decimal_exactness_on_awkward_totals(db):
    store, product = build_product(db, detail="33.33", gros="20.00", super_gros="0.10")
    sale = checkout(db, store, [{"product_id": product.id, "quantity": 3}])
    assert sale.total_amount == Decimal("99.99")

    store2, p2 = build_product(db, detail="14.29", gros="10.00", super_gros="0.10")
    sale2 = checkout(db, store2, [{"product_id": p2.id, "quantity": 7}])
    assert sale2.total_amount == Decimal("100.03")
    # Round-trip from storage stays exact
    db.expire_all()
    stored = db.get(Sale, sale2.id)
    assert stored.total_amount == Decimal("100.03")


def test_db_check_constraint_backstops_negative_stock(db):
    _, product = build_product(db, stock=2)
    with pytest.raises(IntegrityError):
        db.execute(
            update(Product).where(Product.id == product.id).values(stock_quantity=-1)
        )
    db.rollback()


# ------------------------------------------------- race condition (closed)


def test_two_sessions_competing_for_last_units(tmp_path):
    """Both sessions 'see' the last unit available (stale read), but the
    conditional UPDATE lets exactly one win; the other is rejected."""
    engine = create_engine(f"sqlite:///{tmp_path / 'race.db'}")
    Base.metadata.create_all(engine)
    SessionFactory = sessionmaker(bind=engine, autoflush=False)

    with Session(engine) as setup:
        store, product = build_product(setup, stock=1)
        store_id, product_id = store.id, product.id

    s1, s2 = SessionFactory(), SessionFactory()
    try:
        # Both sessions read the product first — the classic stale check.
        p1 = s1.scalar(select(Product).where(Product.id == product_id))
        p2 = s2.scalar(select(Product).where(Product.id == product_id))
        assert p1.stock_quantity == 1 and p2.stock_quantity == 1

        sale = sales.finalize_sale(
            s1,
            CheckoutRequest(
                store_id=store_id,
                items=[CartItem(product_id=product_id, quantity=1)],
            ),
        )
        assert sale.total_amount == Decimal("40.00")

        with pytest.raises(InsufficientStockError):
            sales.finalize_sale(
                s2,
                CheckoutRequest(
                    store_id=store_id,
                    items=[CartItem(product_id=product_id, quantity=1)],
                ),
            )

        with Session(engine) as check:
            final = check.scalar(select(Product).where(Product.id == product_id))
            assert final.stock_quantity == 0  # exactly one sale went through
            assert len(check.scalars(select(Sale)).all()) == 1
    finally:
        s1.close()
        s2.close()
        engine.dispose()
