"""Priced packagings (cartons) — behaviour at checkout.

A packaging is an alternative sale unit of a product with its OWN price
triplet and a unit_count = base stock units consumed per package. Selling
one "Carton" (unit_count=24) charges the carton price (not unit*24) and
deducts 24 base units. Floor and price ordering are per-packaging.
"""

from decimal import Decimal

import pytest

from app.core.exceptions import (
    InsufficientStockError,
    InvalidPriceLevelsError,
    NotFoundError,
    PriceBelowFloorError,
)
from app.models import Sale, SaleItem
from app.schemas.category import CategoryCreate
from app.schemas.product import PackagingCreate, ProductCreate, ProductUpdate
from app.schemas.sale import CartItem, CheckoutRequest
from app.schemas.store import StoreCreate
from app.services import categories, products, sales, stores


def _packaging(label, unit_count, detail, gros, super_gros, position=0):
    return PackagingCreate(
        label=label,
        unit_count=unit_count,
        price_detail=Decimal(detail),
        price_gros=Decimal(gros),
        price_super_gros=Decimal(super_gros),
        position=position,
    )


def build(db, *, stock=1000, packagings=None):
    store = stores.create_store(db, StoreCreate(name="Boutique"))
    product = products.create_product(
        db,
        ProductCreate(
            store_id=store.id,
            name="dikor",
            barcode="B1",
            cost_price=Decimal("10.00"),
            price_detail=Decimal("100.00"),
            price_gros=Decimal("100.00"),
            price_super_gros=Decimal("100.00"),
            stock_quantity=stock,
            packagings=packagings,
        ),
    )
    return store, product


def _checkout(db, store, lines):
    return sales.finalize_sale(
        db,
        CheckoutRequest(
            store_id=store.id, items=[CartItem(**line) for line in lines]
        ),
    )


# --------------------------------------------------------------- creation


def test_product_returns_packagings_in_list_order(db):
    """The list order the client sends defines the display order (the
    service assigns position=index); it round-trips stably."""
    _, product = build(
        db,
        packagings=[
            _packaging("Boîte", 12, "1100.00", "1080.00", "1050.00"),
            _packaging("Carton", 24, "2100.00", "2050.00", "2000.00"),
        ],
    )
    labels = [p.label for p in product.packagings]
    assert labels == ["Boîte", "Carton"]
    assert [p.position for p in product.packagings] == [0, 1]


def test_packaging_price_ordering_violation_rejected(db):
    with pytest.raises(InvalidPriceLevelsError):
        build(db, packagings=[_packaging("Carton", 24, "2000.00", "2050.00", "2000.00")])


def test_packaging_unit_count_below_one_rejected(db):
    with pytest.raises(Exception):  # pydantic ge=1 or service/DB CHECK
        _packaging("Bad", 0, "10.00", "10.00", "10.00")


def test_update_packagings_none_leaves_unchanged_empty_clears(db):
    _, product = build(
        db, packagings=[_packaging("Carton", 24, "2100.00", "2050.00", "2000.00")]
    )
    # None -> unchanged
    products.update_product(db, product.id, ProductUpdate(name="dikor 2"))
    refreshed = products.get_product(db, product.id)
    assert len(refreshed.packagings) == 1
    # [] -> cleared
    products.update_product(db, product.id, ProductUpdate(packagings=[]))
    refreshed = products.get_product(db, product.id)
    assert refreshed.packagings == []


# --------------------------------------------------------------- checkout


def test_sell_one_carton_deducts_unit_count_and_charges_package_price(db):
    store, product = build(
        db,
        stock=100,
        packagings=[_packaging("Carton", 24, "2100.00", "2050.00", "2000.00")],
    )
    carton = product.packagings[0]
    sale = _checkout(
        db, store, [{"product_id": product.id, "quantity": 1, "packaging_id": carton.id}]
    )
    db.refresh(product)
    assert product.stock_quantity == 100 - 24  # base units consumed
    item = sale.items[0]
    assert item.unit_price_applied == Decimal("2100.00")  # package price, not unit*24
    assert item.line_total == Decimal("2100.00")
    assert item.packaging_label == "Carton"
    assert item.unit_count == 24
    assert sale.total_amount == Decimal("2100.00")


def test_sell_three_cartons(db):
    store, product = build(
        db,
        stock=100,
        packagings=[_packaging("Carton", 24, "2100.00", "2050.00", "2000.00")],
    )
    carton = product.packagings[0]
    sale = _checkout(
        db, store, [{"product_id": product.id, "quantity": 3, "packaging_id": carton.id}]
    )
    db.refresh(product)
    assert product.stock_quantity == 100 - 72
    assert sale.items[0].line_total == Decimal("6300.00")  # 2100 * 3
    assert sale.total_amount == Decimal("6300.00")


def test_packaging_price_level_resolves_packaging_gros(db):
    store, product = build(
        db,
        packagings=[_packaging("Carton", 24, "2100.00", "2050.00", "2000.00")],
    )
    carton = product.packagings[0]
    sale = _checkout(
        db,
        store,
        [
            {
                "product_id": product.id,
                "quantity": 1,
                "packaging_id": carton.id,
                "price_level": "gros",
            }
        ],
    )
    assert sale.items[0].unit_price_applied == Decimal("2050.00")


def test_override_below_packaging_floor_rejected(db):
    store, product = build(
        db,
        packagings=[_packaging("Carton", 24, "2100.00", "2050.00", "2000.00")],
    )
    carton = product.packagings[0]
    with pytest.raises(PriceBelowFloorError):
        _checkout(
            db,
            store,
            [
                {
                    "product_id": product.id,
                    "quantity": 1,
                    "packaging_id": carton.id,
                    "unit_price_override": Decimal("1999.99"),  # below 2000 floor
                }
            ],
        )


def test_override_at_packaging_floor_allowed(db):
    store, product = build(
        db,
        packagings=[_packaging("Carton", 24, "2100.00", "2050.00", "2000.00")],
    )
    carton = product.packagings[0]
    sale = _checkout(
        db,
        store,
        [
            {
                "product_id": product.id,
                "quantity": 1,
                "packaging_id": carton.id,
                "unit_price_override": Decimal("2000.00"),
            }
        ],
    )
    assert sale.items[0].unit_price_applied == Decimal("2000.00")


def test_insufficient_stock_for_carton_deducts_nothing(db):
    store, product = build(
        db,
        stock=20,  # less than one carton of 24
        packagings=[_packaging("Carton", 24, "2100.00", "2050.00", "2000.00")],
    )
    carton = product.packagings[0]
    with pytest.raises(InsufficientStockError):
        _checkout(
            db,
            store,
            [{"product_id": product.id, "quantity": 1, "packaging_id": carton.id}],
        )
    db.refresh(product)
    assert product.stock_quantity == 20  # untouched
    assert db.query(Sale).count() == 0


def test_mixed_cart_base_unit_and_carton(db):
    store, product = build(
        db,
        stock=100,
        packagings=[_packaging("Carton", 24, "2100.00", "2050.00", "2000.00")],
    )
    carton = product.packagings[0]
    sale = _checkout(
        db,
        store,
        [
            {"product_id": product.id, "quantity": 5},  # 5 base units @ 100
            {"product_id": product.id, "quantity": 1, "packaging_id": carton.id},
        ],
    )
    db.refresh(product)
    assert product.stock_quantity == 100 - 5 - 24
    assert sale.total_amount == Decimal("500.00") + Decimal("2100.00")


def test_inactive_or_deleted_packaging_rejected(db):
    store, product = build(
        db,
        packagings=[_packaging("Carton", 24, "2100.00", "2050.00", "2000.00")],
    )
    carton_id = product.packagings[0].id
    # Clear packagings (soft-delete) then try to sell the old id.
    products.update_product(db, product.id, ProductUpdate(packagings=[]))
    with pytest.raises(NotFoundError):
        _checkout(
            db,
            store,
            [{"product_id": product.id, "quantity": 1, "packaging_id": carton_id}],
        )


def test_cross_product_packaging_rejected(db):
    store, product_a = build(
        db,
        packagings=[_packaging("Carton", 24, "2100.00", "2050.00", "2000.00")],
    )
    product_b = products.create_product(
        db,
        ProductCreate(
            store_id=store.id,
            name="Autre",
            cost_price=Decimal("5.00"),
            price_detail=Decimal("50.00"),
            price_gros=Decimal("45.00"),
            price_super_gros=Decimal("40.00"),
            stock_quantity=100,
        ),
    )
    a_carton = product_a.packagings[0].id
    with pytest.raises(NotFoundError):
        _checkout(
            db,
            store,
            [{"product_id": product_b.id, "quantity": 1, "packaging_id": a_carton}],
        )
