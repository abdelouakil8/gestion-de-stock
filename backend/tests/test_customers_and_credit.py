"""Phase 6: customers, credit sales, payments — every rule, service level.

Key invariants: a partial payment always requires a customer; overpayment
is always rejected (never clamped); sale.balance = total − SUM(payments)
stays exact Decimal arithmetic; checkout + stock decrement + payment stay
one atomic transaction."""

from datetime import datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.core.exceptions import (
    CreditRequiresCustomerError,
    CustomerPhoneExistsError,
    InvalidPaymentAmountError,
    NotFoundError,
    OverpaymentError,
)
from app.models import Payment, Sale
from app.schemas.customer import CustomerCreate, CustomerUpdate
from app.schemas.product import ProductCreate
from app.schemas.sale import CartItem, CheckoutRequest, PaymentInfo
from app.schemas.store import StoreCreate
from app.services import customers, payments, products, sales, stores


def make_store(db):
    return stores.create_store(db, StoreCreate(name="Boutique Crédit"))


def make_product(db, store, detail="40.00", stock=100, cost="25.00"):
    return products.create_product(
        db,
        ProductCreate(
            store_id=store.id,
            name="Eau minérale 1.5L",
            cost_price=Decimal(cost),
            price_detail=Decimal(detail),
            price_gros=Decimal(detail),
            price_super_gros=Decimal("0.10"),
            stock_quantity=stock,
        ),
    )


def make_customer(db, store, name="Ali Benali", phone="0550123456"):
    return customers.create_customer(
        db, CustomerCreate(store_id=store.id, name=name, phone=phone)
    )


def checkout(db, store, product, quantity=1, payment=None, price=None):
    return sales.finalize_sale(
        db,
        CheckoutRequest(
            store_id=store.id,
            items=[
                CartItem(
                    product_id=product.id,
                    quantity=quantity,
                    unit_price_override=Decimal(price) if price else None,
                )
            ],
            payment=payment or PaymentInfo(),
        ),
    )


# ------------------------------------------------------------- customers


def test_customer_phone_unique_per_store_among_non_deleted(db):
    store = make_store(db)
    make_customer(db, store)
    with pytest.raises(CustomerPhoneExistsError):
        make_customer(db, store, name="Autre", phone="0550123456")
    db.rollback()

    # Same phone in ANOTHER store is fine (multi-tenant rule).
    other = stores.create_store(db, StoreCreate(name="Autre boutique"))
    make_customer(db, other, phone="0550123456")

    # After soft delete, the phone can be reused in the same store.
    first = customers.list_customers(db, store.id)[0]
    customers.soft_delete_customer(db, first.id)
    make_customer(db, store, name="Successeur", phone="0550123456")


def test_customer_update_phone_conflict_rejected(db):
    store = make_store(db)
    c1 = make_customer(db, store, phone="0550000001")
    c2 = make_customer(db, store, name="Brahim", phone="0550000002")
    with pytest.raises(CustomerPhoneExistsError):
        customers.update_customer(db, c2.id, CustomerUpdate(phone="0550000001"))
    # Updating a customer to their own phone is not a conflict.
    updated = customers.update_customer(db, c1.id, CustomerUpdate(phone="0550000001"))
    assert updated.phone == "0550000001"


def test_customer_search_by_name_and_phone(db):
    store = make_store(db)
    make_customer(db, store, name="Ali Benali", phone="0550111111")
    make_customer(db, store, name="Brahim Cherif", phone="0660222222")

    assert [c.name for c in customers.list_customers(db, store.id, query="ali")] == [
        "Ali Benali"
    ]
    assert [c.name for c in customers.list_customers(db, store.id, query="0660")] == [
        "Brahim Cherif"
    ]
    assert len(customers.list_customers(db, store.id)) == 2


# ----------------------------------------------------- checkout payments


def test_full_payment_default_creates_payment_row_and_zero_balance(db):
    store = make_store(db)
    product = make_product(db, store)
    sale = checkout(db, store, product, quantity=2)  # 80.00, default full

    assert sale.total_amount == Decimal("80.00")
    assert sale.paid_amount == Decimal("80.00")
    assert sale.balance == Decimal("0.00")
    assert sale.customer_id is None  # walk-in stays anonymous
    rows = db.scalars(select(Payment).where(Payment.sale_id == sale.id)).all()
    assert len(rows) == 1 and rows[0].amount == Decimal("80.00")


def test_partial_payment_without_customer_rejected(db):
    store = make_store(db)
    product = make_product(db, store, stock=10)
    with pytest.raises(CreditRequiresCustomerError) as exc:
        checkout(
            db,
            store,
            product,
            payment=PaymentInfo(mode="partial", amount_paid=Decimal("10.00")),
        )
    assert exc.value.code == "credit_requires_customer"
    db.rollback()
    db.refresh(product)
    assert product.stock_quantity == 10  # nothing committed
    assert db.scalar(select(Sale)) is None


def test_partial_payment_with_unknown_or_foreign_customer_rejected(db):
    store = make_store(db)
    product = make_product(db, store)
    with pytest.raises(NotFoundError):
        checkout(
            db,
            store,
            product,
            payment=PaymentInfo(
                mode="partial", amount_paid=Decimal("10.00"), customer_id=uuid4()
            ),
        )
    db.rollback()
    # A customer of another store is just as unknown here.
    other = stores.create_store(db, StoreCreate(name="Autre"))
    foreign = make_customer(db, other)
    with pytest.raises(NotFoundError):
        checkout(
            db,
            store,
            product,
            payment=PaymentInfo(
                mode="partial", amount_paid=Decimal("10.00"), customer_id=foreign.id
            ),
        )
    db.rollback()


def test_partial_amount_must_be_below_total(db):
    store = make_store(db)
    product = make_product(db, store)
    customer = make_customer(db, store)

    for amount in ("40.00", "45.00"):  # == total and > total both rejected
        with pytest.raises(InvalidPaymentAmountError):
            checkout(
                db,
                store,
                product,
                payment=PaymentInfo(
                    mode="partial",
                    amount_paid=Decimal(amount),
                    customer_id=customer.id,
                ),
            )
        db.rollback()

    # Missing amount is rejected too.
    with pytest.raises(InvalidPaymentAmountError):
        checkout(
            db,
            store,
            product,
            payment=PaymentInfo(mode="partial", customer_id=customer.id),
        )
    db.rollback()

    # Negative amounts never pass the schema (Money is ge=0).
    with pytest.raises(ValidationError):
        PaymentInfo(mode="partial", amount_paid=Decimal("-1.00"))


def test_partial_payment_happy_path_is_atomic_with_stock(db):
    store = make_store(db)
    product = make_product(db, store, stock=10)
    customer = make_customer(db, store)

    sale = checkout(
        db,
        store,
        product,
        quantity=3,  # total 120.00
        payment=PaymentInfo(
            mode="partial", amount_paid=Decimal("50.00"), customer_id=customer.id
        ),
    )
    assert sale.total_amount == Decimal("120.00")
    assert sale.paid_amount == Decimal("50.00")
    assert sale.balance == Decimal("70.00")
    assert sale.customer_id == customer.id
    db.refresh(product)
    assert product.stock_quantity == 7

    rows = payments.list_payments(db, sale.id)
    assert len(rows) == 1 and rows[0].amount == Decimal("50.00")


def test_partial_payment_of_zero_means_pure_credit(db):
    store = make_store(db)
    product = make_product(db, store)
    customer = make_customer(db, store)
    sale = checkout(
        db,
        store,
        product,
        payment=PaymentInfo(
            mode="partial", amount_paid=Decimal("0.00"), customer_id=customer.id
        ),
    )
    assert sale.paid_amount == Decimal("0.00")
    assert sale.balance == sale.total_amount == Decimal("40.00")
    assert payments.list_payments(db, sale.id) == []  # amount 0: no row


def test_full_payment_can_still_attach_a_customer(db):
    store = make_store(db)
    product = make_product(db, store)
    customer = make_customer(db, store)
    sale = checkout(
        db, store, product, payment=PaymentInfo(mode="full", customer_id=customer.id)
    )
    assert sale.customer_id == customer.id
    assert sale.balance == Decimal("0.00")


# -------------------------------------------------------- later payments


def make_credit_sale(db, store, product, customer, paid="50.00", quantity=3):
    return checkout(
        db,
        store,
        product,
        quantity=quantity,  # 120.00 at detail 40
        payment=PaymentInfo(
            mode="partial", amount_paid=Decimal(paid), customer_id=customer.id
        ),
    )


def test_settlement_flow_partial_then_full(db):
    store = make_store(db)
    product = make_product(db, store)
    customer = make_customer(db, store)
    sale = make_credit_sale(db, store, product, customer)  # 120 total, 50 paid

    payments.record_payment(db, sale.id, Decimal("30.00"))
    db.refresh(sale)
    assert sale.paid_amount == Decimal("80.00")
    assert sale.balance == Decimal("40.00")

    payments.record_payment(db, sale.id, Decimal("40.00"))  # exact settlement
    db.refresh(sale)
    assert sale.paid_amount == Decimal("120.00")
    assert sale.balance == Decimal("0.00")

    # Full history is auditable: checkout payment + two instalments.
    history = payments.list_payments(db, sale.id)
    assert [p.amount for p in history] == [
        Decimal("50.00"),
        Decimal("30.00"),
        Decimal("40.00"),
    ]


def test_overpayment_rejected_never_clamped(db):
    store = make_store(db)
    product = make_product(db, store)
    customer = make_customer(db, store)
    sale = make_credit_sale(db, store, product, customer)  # balance 70

    with pytest.raises(OverpaymentError) as exc:
        payments.record_payment(db, sale.id, Decimal("70.01"))
    assert exc.value.code == "overpayment"
    db.refresh(sale)
    assert sale.paid_amount == Decimal("50.00")  # untouched
    assert len(payments.list_payments(db, sale.id)) == 1

    # A payment on an already settled sale is an overpayment too.
    payments.record_payment(db, sale.id, Decimal("70.00"))
    with pytest.raises(OverpaymentError):
        payments.record_payment(db, sale.id, Decimal("0.01"))


def test_payment_amount_must_be_positive_and_sale_must_exist(db):
    store = make_store(db)
    product = make_product(db, store)
    customer = make_customer(db, store)
    sale = make_credit_sale(db, store, product, customer)

    for amount in (Decimal("0.00"), Decimal("-5.00")):
        with pytest.raises(InvalidPaymentAmountError):
            payments.record_payment(db, sale.id, amount)
    with pytest.raises(NotFoundError):
        payments.record_payment(db, uuid4(), Decimal("1.00"))


def test_balance_math_exact_with_awkward_decimals(db):
    store = make_store(db)
    product = make_product(db, store, detail="14.29")
    customer = make_customer(db, store)
    sale = checkout(
        db,
        store,
        product,
        quantity=7,  # 100.03 exactly
        payment=PaymentInfo(
            mode="partial", amount_paid=Decimal("33.34"), customer_id=customer.id
        ),
    )
    assert sale.total_amount == Decimal("100.03")
    assert sale.balance == Decimal("66.69")

    payments.record_payment(db, sale.id, Decimal("66.68"))
    db.refresh(sale)
    assert sale.balance == Decimal("0.01")  # exact to the cent

    payments.record_payment(db, sale.id, Decimal("0.01"))
    db.expire_all()
    stored = db.get(Sale, sale.id)
    assert stored.paid_amount == Decimal("100.03")
    assert stored.balance == Decimal("0.00")
    # Invariant: cache always equals the audited payment history.
    assert sum(p.amount for p in payments.list_payments(db, sale.id)) == Decimal(
        "100.03"
    )


# ------------------------------------------------------------- analytics


def test_customer_stats_revenue_profit_balance_and_last_purchase(db):
    store = make_store(db)
    product = make_product(db, store, detail="40.00", cost="25.00")
    customer = make_customer(db, store)

    s1 = checkout(
        db,
        store,
        product,
        quantity=2,
        payment=PaymentInfo(mode="full", customer_id=customer.id),
    )  # 80.00, profit 30.00
    s1.created_at = datetime(2026, 1, 10, 10, 0)
    db.commit()
    s2 = make_credit_sale(db, store, product, customer)  # 120.00, paid 50
    s2.created_at = datetime(2026, 3, 5, 10, 0)
    db.commit()

    stats = customers.customer_stats(db, customer.id)
    assert stats.total_revenue == Decimal("200.00")
    assert stats.total_profit == Decimal("75.00")  # (40-25) x 5
    assert stats.sales_count == 2
    assert stats.outstanding_balance == Decimal("70.00")
    assert stats.last_purchase_at == datetime(2026, 3, 5, 10, 0)

    # Soft-deleted sales disappear from the figures.
    sales.soft_delete_sale(db, s2.id)
    stats = customers.customer_stats(db, customer.id)
    assert stats.total_revenue == Decimal("80.00")
    assert stats.outstanding_balance == Decimal("0.00")
    assert stats.sales_count == 1


def test_top_customers_ranked_by_revenue_over_range(db):
    store = make_store(db)
    product = make_product(db, store, stock=1000)
    big = make_customer(db, store, name="Gros client", phone="0770000001")
    small = make_customer(db, store, name="Petit client", phone="0770000002")
    jan = datetime(2026, 1, 15, 12, 0)

    for customer, qty in ((big, 5), (small, 1), (big, 3)):
        sale = checkout(
            db,
            store,
            product,
            quantity=qty,
            payment=PaymentInfo(mode="full", customer_id=customer.id),
        )
        sale.created_at = jan
        db.commit()

    top = customers.top_customers(
        db, store.id, datetime(2026, 1, 1), datetime(2026, 1, 31, 23, 59, 59)
    )
    assert [t.name for t in top] == ["Gros client", "Petit client"]
    assert top[0].revenue == Decimal("320.00")  # (5+3) x 40
    assert top[0].sales_count == 2

    # Out-of-range: nothing.
    assert (
        customers.top_customers(
            db, store.id, datetime(2026, 2, 1), datetime(2026, 2, 28)
        )
        == []
    )
