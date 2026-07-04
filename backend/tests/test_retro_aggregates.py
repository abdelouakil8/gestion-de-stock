"""Customer aggregates must flow through retro-assignment.

A guest (no-customer) sale carries revenue, profit and any outstanding
balance the moment it is assigned to a customer — and disappears from that
customer's figures is impossible because assignment is one-way (never a
reassign). These tests drive the *service* builders to seed data and the
*HTTP* surface (statistics + alerts) to read the aggregates back, both over
one shared in-memory database so an assignment made through the API is
visible to the analytics queries and vice-versa.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.core.config import settings
from app.core.security import hash_pin
from app.main import app
from app.models import Base
from app.schemas.customer import CustomerCreate
from app.schemas.product import ProductCreate
from app.schemas.sale import CartItem, CheckoutRequest, PaymentInfo
from app.schemas.store import StoreCreate
from app.services import customers, products, sales, stores

PIN = "1234"
PIN_HEADER = {"X-Owner-Pin": PIN}


@pytest.fixture()
def env(monkeypatch):
    """One in-memory DB shared by the service builders (``session``) and the
    HTTP client. The client's ``get_db`` is overridden to the very same
    Session so a POST /sales/{id}/customer and a GET /statistics/... read
    and write the same rows."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)

    monkeypatch.setattr(settings, "pin_hash", hash_pin(PIN))
    app.dependency_overrides[deps.get_db] = lambda: session
    with TestClient(app, raise_server_exceptions=False) as client:
        yield session, client
    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


# --------------------------------------------------------------- builders


def make_store(db):
    return stores.create_store(db, StoreCreate(name="Boutique Rétro"))


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
    """A guest checkout by default (no customer_id in the payment)."""
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


def _window_covering(sale):
    """A [date_from, date_to] pair (as ISO date strings) that brackets the
    day the sale was created — robust to the DB clock / timezone."""
    day = sale.created_at.date()
    return (day - timedelta(days=1)).isoformat(), (day + timedelta(days=1)).isoformat()


def customer_stats(client, customer_id):
    resp = client.get(f"/api/v1/statistics/customers/{customer_id}", headers=PIN_HEADER)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ----------------------------------------------------------------- tests


def test_guest_sale_carries_nothing_until_assigned(env):
    """Pre-assignment the customer exists but is empty: revenue 0, no sales,
    nothing outstanding."""
    session, client = env
    store = make_store(session)
    product = make_product(session, store)  # 40 sell / 25 cost -> 15 profit/unit
    customer = make_customer(session, store)

    checkout(session, store, product, quantity=2)  # 80.00, full-paid guest sale

    stats = customer_stats(client, customer.id)
    assert stats["total_revenue"] == "0.00"
    assert stats["sales_count"] == 0
    assert stats["outstanding_balance"] == "0.00"
    assert stats["last_purchase_at"] is None


def test_assignment_moves_revenue_and_last_purchase_onto_customer(env):
    session, client = env
    store = make_store(session)
    product = make_product(session, store)
    customer = make_customer(session, store)

    sale = checkout(session, store, product, quantity=2)  # 80.00, fully paid
    assert sale.customer_id is None

    resp = client.post(
        f"/api/v1/sales/{sale.id}/customer", json={"customer_id": str(customer.id)}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["customer_id"] == str(customer.id)

    stats = customer_stats(client, customer.id)
    assert stats["total_revenue"] == str(sale.total_amount)  # "80.00"
    assert stats["total_profit"] == "30.00"  # 15 profit/unit x 2
    assert stats["sales_count"] == 1
    assert stats["outstanding_balance"] == "0.00"
    assert stats["last_purchase_at"] is not None


def test_two_assigned_guest_sales_both_count(env):
    session, client = env
    store = make_store(session)
    product = make_product(session, store)
    customer = make_customer(session, store)

    s1 = checkout(session, store, product, quantity=2)  # 80.00
    s2 = checkout(session, store, product, quantity=3)  # 120.00

    for sale in (s1, s2):
        resp = client.post(
            f"/api/v1/sales/{sale.id}/customer",
            json={"customer_id": str(customer.id)},
        )
        assert resp.status_code == 200, resp.text

    stats = customer_stats(client, customer.id)
    assert stats["sales_count"] == 2
    assert stats["total_revenue"] == str(s1.total_amount + s2.total_amount)  # "200.00"


def test_second_assignment_is_rejected_and_never_reassigns(env):
    """Assignment is one-way. A second POST to a different customer 409s and
    the other customer's figures stay empty."""
    session, client = env
    store = make_store(session)
    product = make_product(session, store)
    c = make_customer(session, store, name="Client C", phone="0550000001")
    d = make_customer(session, store, name="Client D", phone="0550000002")

    sale = checkout(session, store, product, quantity=2)  # 80.00
    first = client.post(
        f"/api/v1/sales/{sale.id}/customer", json={"customer_id": str(c.id)}
    )
    assert first.status_code == 200, first.text

    second = client.post(
        f"/api/v1/sales/{sale.id}/customer", json={"customer_id": str(d.id)}
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "sale_customer_already_set"

    # C keeps the sale; D never gains anything.
    assert customer_stats(client, c.id)["sales_count"] == 1
    d_stats = customer_stats(client, d.id)
    assert d_stats["sales_count"] == 0
    assert d_stats["total_revenue"] == "0.00"


def test_top_customers_lists_customer_only_after_assignment(env):
    session, client = env
    store = make_store(session)
    product = make_product(session, store)
    customer = make_customer(session, store)

    sale = checkout(session, store, product, quantity=2)  # 80.00 guest sale
    date_from, date_to = _window_covering(sale)
    params = {"store_id": str(store.id), "date_from": date_from, "date_to": date_to}

    before = client.get(
        "/api/v1/statistics/top-customers", params=params, headers=PIN_HEADER
    )
    assert before.status_code == 200, before.text
    assert before.json() == []  # a guest sale ranks no customer

    resp = client.post(
        f"/api/v1/sales/{sale.id}/customer", json={"customer_id": str(customer.id)}
    )
    assert resp.status_code == 200, resp.text

    after = client.get(
        "/api/v1/statistics/top-customers", params=params, headers=PIN_HEADER
    )
    assert after.status_code == 200, after.text
    ranked = after.json()
    assert [row["customer_id"] for row in ranked] == [str(customer.id)]
    assert ranked[0]["revenue"] == str(sale.total_amount)  # "80.00"
    assert ranked[0]["sales_count"] == 1


def test_fully_paid_assigned_sale_is_not_an_outstanding_credit(env):
    """Assigning a *fully paid* sale must not conjure a debt: it stays out of
    the alerts' outstanding_credits list."""
    session, client = env
    store = make_store(session)
    product = make_product(session, store)
    customer = make_customer(session, store)

    sale = checkout(session, store, product, quantity=2)  # 80.00 paid in full
    assert sale.balance == Decimal("0.00")

    resp = client.post(
        f"/api/v1/sales/{sale.id}/customer", json={"customer_id": str(customer.id)}
    )
    assert resp.status_code == 200, resp.text

    alerts = client.get("/api/v1/alerts", params={"store_id": str(store.id)})
    assert alerts.status_code == 200, alerts.text
    body = alerts.json()
    outstanding_ids = [row["sale_id"] for row in body["outstanding_credits"]]
    assert str(sale.id) not in outstanding_ids
    assert body["summary"]["outstanding_credits_count"] == 0
