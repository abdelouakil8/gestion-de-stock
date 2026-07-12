"""Product reservations / layaway (Phase 19).

A reservation holds stock (reserved_quantity) without decrementing it, blocks
that quantity from the caisse, and either converts to a Sale (complete) or
releases the hold (cancel). Manager floor is exercised via the legacy owner
bridge; open mode keeps plain checkout public.
"""

from datetime import UTC, datetime, timedelta

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

PIN = "1234"
OWNER = {"X-Owner-Pin": PIN}


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    monkeypatch.setattr(settings, "pin_hash", hash_pin(PIN))
    app.dependency_overrides[deps.get_db] = lambda: session
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


def _setup(client) -> dict:
    store = client.post("/api/v1/stores", json={"name": "B"}).json()
    product = client.post(
        "/api/v1/products",
        json={
            "store_id": store["id"],
            "name": "Vélo",
            "cost_price": "100.00",
            "price_detail": "500.00",
            "price_gros": "480.00",
            "price_super_gros": "450.00",
            "stock_quantity": 5,
        },
        headers=OWNER,
    ).json()
    customer = client.post(
        "/api/v1/customers",
        json={"store_id": store["id"], "name": "Sam", "phone": "0555111222"},
    ).json()
    return {"store_id": store["id"], "product": product, "customer": customer}


def _reserve(client, s, qty=2, deposit="100.00") -> dict:
    return client.post(
        "/api/v1/reservations",
        json={
            "store_id": s["store_id"],
            "customer_id": s["customer"]["id"],
            "expires_at": (datetime.now(UTC) + timedelta(days=7)).isoformat(),
            "deposit_amount": deposit,
            "items": [{"product_id": s["product"]["id"], "quantity": qty}],
        },
        headers=OWNER,
    )


def test_reservation_holds_stock_and_blocks_caisse(client):
    s = _setup(client)
    r = _reserve(client, s, qty=4)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "active"
    assert body["total_amount"] == "2000.00"  # 4 × 500
    assert body["customer_name"] == "Sam"

    # 4 of 5 held → available is 1. A sale of 2 is refused (insufficient).
    oversell = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": s["store_id"],
            "items": [{"product_id": s["product"]["id"], "quantity": 2}],
        },
    )
    assert oversell.status_code == 409
    assert oversell.json()["error"]["code"] == "insufficient_stock"

    # A sale of the 1 remaining available unit succeeds.
    ok = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": s["store_id"],
            "items": [{"product_id": s["product"]["id"], "quantity": 1}],
        },
    )
    assert ok.status_code == 201, ok.text


def test_cannot_reserve_more_than_available(client):
    s = _setup(client)
    assert _reserve(client, s, qty=3).status_code == 201
    # 3 held of 5 → only 2 available; reserving 3 more fails.
    too_many = _reserve(client, s, qty=3)
    assert too_many.status_code == 409
    assert too_many.json()["error"]["code"] == "insufficient_stock"


def test_complete_converts_to_sale_and_releases_hold(client):
    s = _setup(client)
    reservation = _reserve(client, s, qty=2).json()

    done = client.post(
        f"/api/v1/reservations/{reservation['id']}/complete",
        json={"payment": {"mode": "full"}},
        headers=OWNER,
    )
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "completed"
    assert body["sale_id"] is not None

    # The sale exists with the reservation's total, and stock dropped 5 → 3,
    # with the hold released (reserved back to 0 → available 3).
    sale = client.get(f"/api/v1/sales/{body['sale_id']}").json()
    assert sale["total_amount"] == "1000.00"
    product = client.get("/api/v1/products", params={"store_id": s["store_id"]}).json()[
        0
    ]
    assert product["stock_quantity"] == 3
    assert product["reserved_quantity"] == 0


def test_cancel_releases_hold(client):
    s = _setup(client)
    reservation = _reserve(client, s, qty=4).json()
    cancelled = client.post(
        f"/api/v1/reservations/{reservation['id']}/cancel", headers=OWNER
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["status"] == "cancelled"

    # Hold released → the full 5 are available again for the caisse.
    ok = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": s["store_id"],
            "items": [{"product_id": s["product"]["id"], "quantity": 5}],
        },
    )
    assert ok.status_code == 201, ok.text

    # A cancelled reservation cannot be completed.
    again = client.post(
        f"/api/v1/reservations/{reservation['id']}/complete",
        json={"payment": {"mode": "full"}},
        headers=OWNER,
    )
    assert again.status_code == 409
    assert again.json()["error"]["code"] == "reservation_not_active"


def test_reservation_requires_manager(client):
    s = _setup(client)
    # No auth, but named users don't exist -> manager routes never fall open.
    r = client.post(
        "/api/v1/reservations",
        json={
            "store_id": s["store_id"],
            "customer_id": s["customer"]["id"],
            "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            "items": [{"product_id": s["product"]["id"], "quantity": 1}],
        },
    )
    assert r.status_code == 401
