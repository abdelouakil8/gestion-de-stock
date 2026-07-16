"""Tests for the refund (avoir) feature — full, partial, over-refund, credit cap."""

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
PIN_HEADER = {"X-Owner-Pin": PIN}


@pytest.fixture()
def client(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)

    monkeypatch.setattr(settings, "pin_hash", hash_pin(PIN))
    app.dependency_overrides[deps.get_db] = lambda: session
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


def _make_sale(client, qty: int = 5, price: str = "40.00") -> dict:
    """Create a store, product, and a sale for testing refunds."""
    store = client.post("/api/v1/stores", json={"name": "Test"}).json()
    product = client.post(
        "/api/v1/products",
        json={
            "store_id": store["id"],
            "name": "Widget",
            "price_detail": price,
            "price_gros": price,
            "price_super_gros": price,
            "cost_price": "20.00",
            "stock_quantity": 100,
            "low_stock_threshold": 5,
        },
        headers=PIN_HEADER,
    ).json()
    sale = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": store["id"],
            "items": [
                {
                    "product_id": product["id"],
                    "quantity": qty,
                    "price_level": "detail",
                }
            ],
        },
    ).json()
    return {
        "store": store,
        "product": product,
        "sale": sale,
        "sale_item_id": sale["items"][0]["id"],
    }


def _make_discounted_sale(
    client, qty: int = 2, price: str = "100.00", discount: str = "40.00"
) -> dict:
    """A sale whose single line carries a raw line discount, so the net paid
    (line_total) is strictly less than gross price*qty."""
    store = client.post("/api/v1/stores", json={"name": "TestDisc"}).json()
    product = client.post(
        "/api/v1/products",
        json={
            "store_id": store["id"],
            "name": "Widget remisé",
            "price_detail": price,
            "price_gros": price,
            # Low floor so the line discount stays above price_super_gros.
            "price_super_gros": "50.00",
            "cost_price": "20.00",
            "stock_quantity": 100,
            "low_stock_threshold": 5,
        },
        headers=PIN_HEADER,
    ).json()
    sale = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": store["id"],
            "items": [
                {
                    "product_id": product["id"],
                    "quantity": qty,
                    "price_level": "detail",
                    "discount_amount": discount,
                }
            ],
        },
    ).json()
    return {
        "store": store,
        "product": product,
        "sale": sale,
        "sale_item_id": sale["items"][0]["id"],
    }


class TestRefundHonoursDiscount:
    """Regression: a refund must return the NET amount the customer paid, not
    the gross list price. Refunding the gross price on a discounted line either
    hands back too much cash or wrongly rejects a legitimate full return."""

    def test_full_refund_of_discounted_line_returns_net(self, client):
        # price 100 x qty 2 - discount 40 = 160 net paid.
        data = _make_discounted_sale(client, qty=2, price="100.00", discount="40.00")
        assert data["sale"]["total_amount"] == "160.00"
        resp = client.post(
            f"/api/v1/sales/{data['sale']['id']}/refund",
            json={"items": [{"sale_item_id": data["sale_item_id"], "quantity": 2}]},
            headers=PIN_HEADER,
        )
        # Old (gross) code computed 100*2 = 200 > paid 160 and wrongly 409'd.
        assert resp.status_code == 201, resp.text
        assert resp.json()["total_amount"] == "160.00"  # net, not 200.00

    def test_partial_refund_of_discounted_line_is_prorated(self, client):
        data = _make_discounted_sale(client, qty=2, price="100.00", discount="40.00")
        resp = client.post(
            f"/api/v1/sales/{data['sale']['id']}/refund",
            json={"items": [{"sale_item_id": data["sale_item_id"], "quantity": 1}]},
            headers=PIN_HEADER,
        )
        assert resp.status_code == 201, resp.text
        # Net per unit = 160 / 2 = 80, not the gross 100.
        assert resp.json()["total_amount"] == "80.00"


class TestRefundCreation:
    def test_full_refund(self, client):
        data = _make_sale(client, qty=3)
        resp = client.post(
            f"/api/v1/sales/{data['sale']['id']}/refund",
            json={
                "items": [{"sale_item_id": data["sale_item_id"], "quantity": 3}],
                "reason": "Retour complet",
            },
            headers=PIN_HEADER,
        )
        assert resp.status_code == 201
        refund = resp.json()
        assert refund["total_amount"] == "120.00"
        assert refund["reason"] == "Retour complet"
        assert len(refund["items"]) == 1
        assert refund["items"][0]["quantity"] == 3

    def test_partial_refund(self, client):
        data = _make_sale(client, qty=5)
        resp = client.post(
            f"/api/v1/sales/{data['sale']['id']}/refund",
            json={"items": [{"sale_item_id": data["sale_item_id"], "quantity": 2}]},
            headers=PIN_HEADER,
        )
        assert resp.status_code == 201
        refund = resp.json()
        assert refund["total_amount"] == "80.00"

    def test_stock_restored(self, client):
        data = _make_sale(client, qty=5)
        # Stock was 100, sold 5 -> 95. Refund 3 -> should be 98.
        client.post(
            f"/api/v1/sales/{data['sale']['id']}/refund",
            json={"items": [{"sale_item_id": data["sale_item_id"], "quantity": 3}]},
            headers=PIN_HEADER,
        )
        product = client.get(
            f"/api/v1/products/{data['product']['id']}/details",
            headers=PIN_HEADER,
        ).json()
        assert product["stock_quantity"] == 98

    def test_over_refund_rejected(self, client):
        data = _make_sale(client, qty=3)
        resp = client.post(
            f"/api/v1/sales/{data['sale']['id']}/refund",
            json={"items": [{"sale_item_id": data["sale_item_id"], "quantity": 4}]},
            headers=PIN_HEADER,
        )
        assert resp.status_code == 409
        body = resp.json()
        assert body["error"]["code"] == "refund_exceeds_quantity"

    def test_multiple_partial_refunds(self, client):
        data = _make_sale(client, qty=5)
        # First refund: 2 units.
        resp1 = client.post(
            f"/api/v1/sales/{data['sale']['id']}/refund",
            json={"items": [{"sale_item_id": data["sale_item_id"], "quantity": 2}]},
            headers=PIN_HEADER,
        )
        assert resp1.status_code == 201
        # Second refund: 2 more units.
        resp2 = client.post(
            f"/api/v1/sales/{data['sale']['id']}/refund",
            json={"items": [{"sale_item_id": data["sale_item_id"], "quantity": 2}]},
            headers=PIN_HEADER,
        )
        assert resp2.status_code == 201
        # Third attempt: only 1 left, asking for 2 should fail.
        resp3 = client.post(
            f"/api/v1/sales/{data['sale']['id']}/refund",
            json={"items": [{"sale_item_id": data["sale_item_id"], "quantity": 2}]},
            headers=PIN_HEADER,
        )
        assert resp3.status_code == 409

    def test_refund_exceeds_paid_amount(self, client):
        """Credit sale: refund cannot exceed what was actually paid."""
        store = client.post("/api/v1/stores", json={"name": "Test"}).json()
        customer = client.post(
            "/api/v1/customers",
            json={"store_id": store["id"], "name": "Ali", "phone": "0555000111"},
        ).json()
        product = client.post(
            "/api/v1/products",
            json={
                "store_id": store["id"],
                "name": "Expensive",
                "price_detail": "100.00",
                "price_gros": "100.00",
                "price_super_gros": "100.00",
                "cost_price": "50.00",
                "stock_quantity": 50,
                "low_stock_threshold": 5,
            },
            headers=PIN_HEADER,
        ).json()
        # Credit sale: total=500, paid=200.
        sale = client.post(
            "/api/v1/sales/checkout",
            json={
                "store_id": store["id"],
                "items": [
                    {
                        "product_id": product["id"],
                        "quantity": 5,
                        "price_level": "detail",
                    }
                ],
                "payment": {
                    "mode": "partial",
                    "amount_paid": "200.00",
                    "customer_id": customer["id"],
                },
            },
        ).json()
        sale_item_id = sale["items"][0]["id"]
        # Refunding 3 units = 300 > paid 200 -> rejected.
        resp = client.post(
            f"/api/v1/sales/{sale['id']}/refund",
            json={"items": [{"sale_item_id": sale_item_id, "quantity": 3}]},
            headers=PIN_HEADER,
        )
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "refund_exceeds_paid"

    def test_requires_pin(self, client):
        data = _make_sale(client, qty=2)
        resp = client.post(
            f"/api/v1/sales/{data['sale']['id']}/refund",
            json={"items": [{"sale_item_id": data["sale_item_id"], "quantity": 1}]},
        )
        assert resp.status_code == 401


class TestRefundableItems:
    def test_shows_available_after_partial(self, client):
        data = _make_sale(client, qty=5)
        client.post(
            f"/api/v1/sales/{data['sale']['id']}/refund",
            json={"items": [{"sale_item_id": data["sale_item_id"], "quantity": 2}]},
            headers=PIN_HEADER,
        )
        resp = client.get(f"/api/v1/sales/{data['sale']['id']}/refundable")
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) == 1
        assert items[0]["available"] == 3
        assert items[0]["already_refunded"] == 2

    def test_empty_when_fully_refunded(self, client):
        data = _make_sale(client, qty=2)
        client.post(
            f"/api/v1/sales/{data['sale']['id']}/refund",
            json={"items": [{"sale_item_id": data["sale_item_id"], "quantity": 2}]},
            headers=PIN_HEADER,
        )
        resp = client.get(f"/api/v1/sales/{data['sale']['id']}/refundable")
        assert resp.status_code == 200
        assert resp.json() == []


class TestRefundList:
    def test_list_refunds(self, client):
        data = _make_sale(client, qty=5)
        client.post(
            f"/api/v1/sales/{data['sale']['id']}/refund",
            json={"items": [{"sale_item_id": data["sale_item_id"], "quantity": 1}]},
            headers=PIN_HEADER,
        )
        client.post(
            f"/api/v1/sales/{data['sale']['id']}/refund",
            json={"items": [{"sale_item_id": data["sale_item_id"], "quantity": 1}]},
            headers=PIN_HEADER,
        )
        resp = client.get(f"/api/v1/sales/{data['sale']['id']}/refunds")
        assert resp.status_code == 200
        assert len(resp.json()) == 2
