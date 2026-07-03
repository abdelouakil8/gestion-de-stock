"""Phase 1 definition-of-done: every model can be created, fetched and
soft-deleted — deleted_at gets set, the row still exists in the table, and
default service queries exclude it. Plus exactness guarantees of Money.

Adapted for Phase 6: PriceTier is gone (named price levels supersede it);
Customer, Payment and StoreSettings joined the data layer."""

from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import StatementError

from app.models import Category, Customer, Payment, Product, Sale, SaleItem, Store
from app.schemas.category import CategoryCreate
from app.schemas.customer import CustomerCreate
from app.schemas.product import ProductCreate
from app.schemas.sale import SaleCreate, SaleItemCreate
from app.schemas.store import StoreCreate
from app.services import categories, customers, products, sales, stores


def make_store(db) -> Store:
    return stores.create_store(db, StoreCreate(name="Boutique Test"))


def make_category(db, store: Store) -> Category:
    return categories.create_category(
        db, CategoryCreate(store_id=store.id, name="Boissons")
    )


def make_product(db, store: Store, category: Category | None = None) -> Product:
    return products.create_product(
        db,
        ProductCreate(
            store_id=store.id,
            category_id=category.id if category else None,
            name="Eau minérale 1.5L",
            barcode="6130000000015",
            cost_price=Decimal("25.00"),
            price_detail=Decimal("40.00"),
            price_gros=Decimal("37.50"),
            price_super_gros=Decimal("30.00"),
            stock_quantity=100,
        ),
    )


def make_customer(db, store: Store, phone="0550123456") -> Customer:
    return customers.create_customer(
        db,
        CustomerCreate(store_id=store.id, name="Ali Benali", phone=phone),
    )


def test_store_crud_and_soft_delete(db):
    store = make_store(db)
    assert stores.get_store(db, store.id) is not None
    assert [s.id for s in stores.list_stores(db)] == [store.id]

    stores.soft_delete_store(db, store.id)
    assert store.deleted_at is not None
    # Row still exists physically…
    assert db.scalar(select(func.count()).select_from(Store)) == 1
    # …but default queries exclude it.
    assert stores.get_store(db, store.id) is None
    assert stores.list_stores(db) == []


def test_category_crud_and_soft_delete(db):
    store = make_store(db)
    category = make_category(db, store)
    assert categories.get_category(db, category.id) is not None
    assert len(categories.list_categories(db, store.id)) == 1

    categories.soft_delete_category(db, category.id)
    assert category.deleted_at is not None
    assert db.scalar(select(func.count()).select_from(Category)) == 1
    assert categories.get_category(db, category.id) is None
    assert categories.list_categories(db, store.id) == []


def test_product_crud_and_soft_delete(db):
    store = make_store(db)
    category = make_category(db, store)
    product = make_product(db, store, category)

    fetched = products.get_product(db, product.id)
    assert fetched is not None
    assert fetched.category_id == category.id
    assert fetched.low_stock_threshold == 5  # default
    assert fetched.image_path is None
    assert len(products.list_products(db, store.id)) == 1

    products.soft_delete_product(db, product.id)
    assert product.deleted_at is not None
    assert db.scalar(select(func.count()).select_from(Product)) == 1
    assert products.get_product(db, product.id) is None
    assert products.list_products(db, store.id) == []


def test_product_money_is_exact_decimal(db):
    store = make_store(db)
    product = make_product(db, store)

    db.expire_all()  # force a reload from the database
    fetched = products.get_product(db, product.id)
    assert isinstance(fetched.cost_price, Decimal)
    assert fetched.cost_price == Decimal("25.00")
    assert isinstance(fetched.price_detail, Decimal)
    assert fetched.price_detail == Decimal("40.00")
    assert fetched.price_gros == Decimal("37.50")
    assert fetched.price_super_gros == Decimal("30.00")


def test_money_rejects_float(db):
    store = make_store(db)
    with pytest.raises(StatementError):
        products.create_product(
            db,
            ProductCreate.model_construct(  # bypass Pydantic to hit the DB guard
                store_id=store.id,
                category_id=None,
                name="Produit flottant",
                barcode=None,
                cost_price=19.99,
                price_detail=Decimal("40.00"),
                price_gros=Decimal("40.00"),
                price_super_gros=Decimal("30.00"),
                stock_quantity=1,
                low_stock_threshold=5,
                is_active=True,
            ),
        )
    db.rollback()


def test_customer_crud_and_soft_delete(db):
    store = make_store(db)
    customer = make_customer(db, store)
    assert customers.get_customer(db, customer.id) is not None
    assert len(customers.list_customers(db, store.id)) == 1

    customers.soft_delete_customer(db, customer.id)
    assert customer.deleted_at is not None
    assert db.scalar(select(func.count()).select_from(Customer)) == 1
    assert customers.get_customer(db, customer.id) is None
    assert customers.list_customers(db, store.id) == []


def test_sale_with_items_crud_and_soft_delete(db):
    store = make_store(db)
    product = make_product(db, store)

    sale = sales.create_sale(
        db,
        SaleCreate(
            store_id=store.id,
            total_amount=Decimal("120.00"),
            items=[
                SaleItemCreate(
                    product_id=product.id,
                    quantity=3,
                    unit_price_applied=Decimal("40.00"),
                    line_total=Decimal("120.00"),
                )
            ],
        ),
    )

    fetched = sales.get_sale(db, sale.id)
    assert fetched is not None
    assert len(fetched.items) == 1
    assert fetched.items[0].line_total == Decimal("120.00")
    assert fetched.items[0].store_id == store.id
    assert fetched.items[0].price_level == "detail"  # default level
    assert len(sales.list_sale_items(db, sale.id)) == 1

    sales.soft_delete_sale(db, sale.id)
    assert sale.deleted_at is not None
    # Financial records are never hard-deleted: both rows still exist.
    assert db.scalar(select(func.count()).select_from(Sale)) == 1
    assert db.scalar(select(func.count()).select_from(SaleItem)) == 1
    assert sales.get_sale(db, sale.id) is None
    assert sales.list_sales(db, store.id) == []
    assert sales.list_sale_items(db, sale.id) == []


def test_payment_rows_are_financial_records(db):
    """Payments persist physically and Money round-trips exactly."""
    from app.schemas.sale import CartItem, CheckoutRequest, PaymentInfo

    store = make_store(db)
    product = make_product(db, store)
    customer = make_customer(db, store)
    sale = sales.finalize_sale(
        db,
        CheckoutRequest(
            store_id=store.id,
            items=[CartItem(product_id=product.id, quantity=1)],
            payment=PaymentInfo(
                mode="partial",
                amount_paid=Decimal("10.50"),
                customer_id=customer.id,
            ),
        ),
    )
    db.expire_all()
    payment = db.scalar(select(Payment).where(Payment.sale_id == sale.id))
    assert isinstance(payment.amount, Decimal)
    assert payment.amount == Decimal("10.50")
    assert db.scalar(select(func.count()).select_from(Payment)) == 1
