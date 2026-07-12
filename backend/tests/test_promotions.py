"""Promotions & discounts (Phase 18).

Line percentage discounts (floor-enforced) and coupon codes (validate preview
+ atomic redemption with max_uses / expiry guards) through the checkout path.
Open mode (no named users) keeps checkout/validate public; owner setup uses the
legacy X-Owner-Pin bridge.
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


def _catalog(client) -> dict:
    store = client.post("/api/v1/stores", json={"name": "B"}).json()
    product = client.post(
        "/api/v1/products",
        json={
            "store_id": store["id"],
            "name": "Eau",
            "cost_price": "25.00",
            "price_detail": "40.00",
            "price_gros": "37.50",
            "price_super_gros": "30.00",
            "stock_quantity": 100,
        },
        headers=OWNER,
    ).json()
    return {"store_id": store["id"], "product": product}


def _promo(client, store_id, **over) -> dict:
    body = {
        "store_id": store_id,
        "code": "promo10",
        "type": "percent",
        "value": "10.00",
        "valid_from": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        "valid_to": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
    }
    body.update(over)
    return client.post("/api/v1/promotions", json=body, headers=OWNER).json()


# ---------------------------------------------------- line % discount


def test_line_percent_discount_applies_and_respects_floor(client):
    cat = _catalog(client)
    store_id, product = cat["store_id"], cat["product"]

    # 10% off detail (40.00) -> line 2×40=80, discount 8.00 -> total 72.00.
    sale = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": store_id,
            "items": [
                {"product_id": product["id"], "quantity": 2, "discount_percent": 10}
            ],
        },
    )
    assert sale.status_code == 201, sale.text
    body = sale.json()
    assert body["total_amount"] == "72.00"
    assert body["items"][0]["discount_amount"] == "8.00"

    # 50% off detail -> 20.00 < 30.00 floor -> rejected.
    below = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": store_id,
            "items": [
                {"product_id": product["id"], "quantity": 1, "discount_percent": 50}
            ],
        },
    )
    assert below.status_code == 409
    assert below.json()["error"]["code"] == "price_below_floor"


# ------------------------------------------------------- coupon codes


def test_promo_validate_and_redeem_reduces_total(client):
    cat = _catalog(client)
    store_id, product = cat["store_id"], cat["product"]
    _promo(client, store_id)

    # Validate preview (does not consume a use).
    preview = client.post(
        "/api/v1/promotions/validate",
        json={"store_id": store_id, "code": "PROMO10", "subtotal": "80.00"},
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["discount"] == "8.00"

    # Checkout with the code: 2×40=80 -> -8.00 -> 72.00 total.
    sale = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": store_id,
            "items": [{"product_id": product["id"], "quantity": 2}],
            "promo_code": "promo10",
        },
    ).json()
    assert sale["total_amount"] == "72.00"
    assert sale["promo_code"] == "PROMO10"
    assert sale["promo_discount"] == "8.00"

    # The list reflects the consumed use.
    promos = client.get(
        "/api/v1/promotions", params={"store_id": store_id}, headers=OWNER
    ).json()
    assert promos[0]["used_count"] == 1


def test_promo_max_uses_is_enforced_atomically(client):
    cat = _catalog(client)
    store_id, product = cat["store_id"], cat["product"]
    _promo(client, store_id, code="single", max_uses=1)

    def _checkout():
        return client.post(
            "/api/v1/sales/checkout",
            json={
                "store_id": store_id,
                "items": [{"product_id": product["id"], "quantity": 1}],
                "promo_code": "single",
            },
        )

    assert _checkout().status_code == 201
    second = _checkout()
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "promo_invalid"


def test_promo_expired_is_rejected(client):
    cat = _catalog(client)
    store_id, product = cat["store_id"], cat["product"]
    _promo(
        client,
        store_id,
        code="old",
        valid_from=(datetime.now(UTC) - timedelta(days=10)).isoformat(),
        valid_to=(datetime.now(UTC) - timedelta(days=1)).isoformat(),
    )
    r = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": store_id,
            "items": [{"product_id": product["id"], "quantity": 1}],
            "promo_code": "old",
        },
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "promo_invalid"


def test_promotion_management_is_owner_only(client):
    cat = _catalog(client)
    # No auth -> creating a promo is refused (owner floor, users may exist? no,
    # but owner routes never fall open) — 401 without the owner bridge.
    r = client.post(
        "/api/v1/promotions",
        json={
            "store_id": cat["store_id"],
            "code": "x",
            "type": "fixed",
            "value": "5.00",
            "valid_from": datetime.now(UTC).isoformat(),
            "valid_to": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
        },
    )
    assert r.status_code == 401
