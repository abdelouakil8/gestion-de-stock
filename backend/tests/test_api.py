"""API tests: TestClient over the real app, business rules via HTTP.

The client deliberately plays a hostile/buggy UI (below-floor overrides,
overselling, bad payloads, missing PIN, credit without customer) and must
always get a structured French error. Adapted for Phase 6: named price
levels replace quantity tiers; customers/credit/alerts/settings endpoints
joined the surface.
"""

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

PIN = "1234"
PIN_HEADER = {"X-Owner-Pin": PIN}


@pytest.fixture()
def client(monkeypatch):
    """TestClient wired to a fresh in-memory DB and a known PIN."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)

    monkeypatch.setattr(settings, "pin_hash", hash_pin(PIN))
    app.dependency_overrides[deps.get_db] = lambda: session
    # raise_server_exceptions=False lets the 500 handler be tested too.
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


def test_set_pin_end_to_end(monkeypatch, tmp_path):
    """POST /auth/set-pin configures the PIN when none exists, 409 afterwards."""
    from app.core.security import verify_pin

    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)

    # No PIN configured yet; isolate the .env write to a temp dir.
    monkeypatch.setattr(settings, "pin_hash", None)
    monkeypatch.setattr("app.api.routes.auth.RUNTIME_DIR", tmp_path)
    app.dependency_overrides[deps.get_db] = lambda: session
    try:
        with TestClient(app, raise_server_exceptions=False) as c:
            assert c.get("/api/v1/auth/status").json() == {"configured": False}

            # First call configures the PIN and returns 200.
            r = c.post("/api/v1/auth/set-pin", json={"pin": "4321"})
            assert r.status_code == 200, r.text
            assert r.json() == {"valid": True}

            # The stored hash actually verifies the PIN (hash-then-verify round trip).
            assert settings.pin_hash is not None
            assert verify_pin("4321", settings.pin_hash)
            assert not verify_pin("0000", settings.pin_hash)

            # Written to the ISOLATED .env, not the real project one.
            env_written = (tmp_path / ".env").read_text("utf-8")
            assert "PIN_HASH=" in env_written

            # The verify endpoint now accepts the freshly-set PIN.
            assert (
                c.post("/api/v1/auth/verify", json={"pin": "4321"}).status_code == 200
            )

            # Second call, PIN already set -> 409 pin_already_configured.
            r2 = c.post("/api/v1/auth/set-pin", json={"pin": "9999"})
            assert r2.status_code == 409
            assert r2.json()["error"]["code"] == "pin_already_configured"
    finally:
        app.dependency_overrides.clear()
        session.close()
        engine.dispose()


def test_version_endpoint(client):
    r = client.get("/api/v1/version")
    assert r.status_code == 200
    data = r.json()
    assert "api_version" in data
    assert "min_frontend_version" in data


def build_catalog(client) -> dict:
    """Store + category + product (40 / 37.50 / 30) via the API itself."""
    store = client.post("/api/v1/stores", json={"name": "Boutique API"}).json()
    category = client.post(
        "/api/v1/categories",
        json={"store_id": store["id"], "name": "Boissons"},
        headers=PIN_HEADER,
    ).json()
    product = client.post(
        "/api/v1/products",
        json={
            "store_id": store["id"],
            "category_id": category["id"],
            "name": "Eau minérale 1.5L",
            "barcode": "6130000000015",
            "cost_price": "25.00",
            "price_detail": "40.00",
            "price_gros": "37.50",
            "price_super_gros": "30.00",
            "stock_quantity": 50,
        },
        headers=PIN_HEADER,
    ).json()
    return {"store": store, "category": category, "product": product}


# ------------------------------------------------------------- happy path


def test_full_happy_path_checkout_and_stats(client):
    cat = build_catalog(client)
    store_id, product = cat["store"]["id"], cat["product"]

    # Cashier list never exposes cost_price but does expose the sale prices.
    listed = client.get("/api/v1/products", params={"store_id": store_id}).json()
    items = listed["items"]
    assert listed["total"] == 1 and len(items) == 1 and "cost_price" not in items[0]
    assert items[0]["price_detail"] == "40.00"
    assert items[0]["price_super_gros"] == "30.00"

    # Barcode lookup (scanner path)
    scanned = client.get(
        "/api/v1/products/by-barcode/6130000000015", params={"store_id": store_id}
    )
    assert scanned.status_code == 200 and scanned.json()["id"] == product["id"]

    # The chosen price level is resolved server-side at checkout.
    sale = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": store_id,
            "items": [
                {"product_id": product["id"], "quantity": 6, "price_level": "gros"}
            ],
        },
    )
    assert sale.status_code == 201
    body = sale.json()
    assert body["total_amount"] == "225.00"  # 6 × 37.50
    assert body["items"][0]["unit_price_applied"] == "37.50"
    assert body["items"][0]["price_level"] == "gros"
    assert body["paid_amount"] == "225.00"  # default full payment
    assert body["balance"] == "0.00"
    assert len(body["payments"]) == 1

    # Stock decremented server-side
    after = client.get(f"/api/v1/products/{product['id']}").json()
    assert after["stock_quantity"] == 44

    # Owner statistics (PIN-gated)
    stats = client.get(
        "/api/v1/statistics/summary",
        params={
            "store_id": store_id,
            "date_from": "2020-01-01",
            "date_to": "2030-01-01",
        },
        headers=PIN_HEADER,
    ).json()
    assert Decimal(stats["revenue"]) == Decimal("225.00")
    assert Decimal(stats["gross_profit"]) == Decimal("75.00")  # (37.50-25)×6

    top = client.get(
        "/api/v1/statistics/top-products",
        params={
            "store_id": store_id,
            "date_from": "2020-01-01",
            "date_to": "2030-01-01",
        },
        headers=PIN_HEADER,
    ).json()
    assert top[0]["name"] == "Eau minérale 1.5L" and top[0]["quantity_sold"] == 6


def test_credit_sale_flow_over_http(client):
    cat = build_catalog(client)
    store_id, product = cat["store"]["id"], cat["product"]

    customer = client.post(
        "/api/v1/customers",
        json={"store_id": store_id, "name": "Ali Benali", "phone": "0550123456"},
    ).json()

    # Partial payment without a customer: specific error code.
    refused = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": store_id,
            "items": [{"product_id": product["id"], "quantity": 2}],
            "payment": {"mode": "partial", "amount_paid": "10.00"},
        },
    )
    assert refused.status_code == 409
    assert refused.json()["error"]["code"] == "credit_requires_customer"

    # With the customer: accepted, balance tracked.
    sale = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": store_id,
            "items": [{"product_id": product["id"], "quantity": 2}],  # 80.00
            "payment": {
                "mode": "partial",
                "amount_paid": "30.00",
                "customer_id": customer["id"],
            },
        },
    ).json()
    assert sale["paid_amount"] == "30.00"
    assert sale["balance"] == "50.00"
    assert sale["customer_id"] == customer["id"]

    # Later payment; overpayment rejected first.
    over = client.post(f"/api/v1/sales/{sale['id']}/payments", json={"amount": "50.01"})
    assert over.status_code == 409
    assert over.json()["error"]["code"] == "overpayment"

    settled = client.post(
        f"/api/v1/sales/{sale['id']}/payments", json={"amount": "50.00"}
    )
    assert settled.status_code == 201
    body = settled.json()
    assert body["balance"] == "0.00"
    assert [p["amount"] for p in body["payments"]] == ["30.00", "50.00"]

    # Alerts no longer list the settled sale.
    alerts = client.get("/api/v1/alerts", params={"store_id": store_id}).json()
    assert alerts["summary"]["outstanding_credits_count"] == 0


def test_settings_roundtrip_over_http(client):
    store = client.post("/api/v1/stores", json={"name": "Boutique Réglages"}).json()

    defaults = client.get("/api/v1/settings", params={"store_id": store["id"]})
    assert defaults.status_code == 200
    assert defaults.json()["ui_language"] == "fr"

    no_pin = client.put(
        "/api/v1/settings",
        params={"store_id": store["id"]},
        json={"shop_name": "Chez Wakil"},
    )
    assert no_pin.status_code == 401

    updated = client.put(
        "/api/v1/settings",
        params={"store_id": store["id"]},
        json={
            "shop_name": "Chez Wakil",
            "ui_language": "ar",
            "theme_accent": "#AA00FF",
        },
        headers=PIN_HEADER,
    )
    assert updated.status_code == 200
    body = client.get("/api/v1/settings", params={"store_id": store["id"]}).json()
    assert body["shop_name"] == "Chez Wakil"
    assert body["ui_language"] == "ar"
    assert body["theme_accent"] == "#AA00FF"

    bad = client.put(
        "/api/v1/settings",
        params={"store_id": store["id"]},
        json={"theme_accent": "rouge"},
        headers=PIN_HEADER,
    )
    assert bad.status_code == 422
    assert bad.json()["error"]["code"] == "validation_error"


# ------------------------------------------------------- business rejections


def test_below_floor_override_rejected_with_409(client):
    cat = build_catalog(client)
    response = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": cat["store"]["id"],
            "items": [
                {
                    "product_id": cat["product"]["id"],
                    "quantity": 1,
                    "unit_price_override": "29.99",
                }
            ],
        },
    )
    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "price_below_floor"
    assert "prix minimum" in error["message"].lower()

    # Nothing was sold, stock untouched
    after = client.get(f"/api/v1/products/{cat['product']['id']}").json()
    assert after["stock_quantity"] == 50


def test_invalid_money_bound_returns_clean_422_not_500(client):
    """A Money field that parses then fails its bound (ge=0) carries a
    Decimal in the pydantic error; the validation handler must JSON-encode
    it (jsonable_encoder) and return 422 — never a 500."""
    cat = build_catalog(client)
    response = client.post(
        "/api/v1/products",
        headers=PIN_HEADER,
        json={
            "store_id": cat["store"]["id"],
            "name": "Prix négatif",
            "cost_price": "-1.00",
            "price_detail": "40.00",
            "price_gros": "37.50",
            "price_super_gros": "30.00",
            "stock_quantity": 1,
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_override_at_exact_floor_allowed(client):
    cat = build_catalog(client)
    response = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": cat["store"]["id"],
            "items": [
                {
                    "product_id": cat["product"]["id"],
                    "quantity": 1,
                    "unit_price_override": "30.00",
                }
            ],
        },
    )
    assert response.status_code == 201
    assert response.json()["total_amount"] == "30.00"


def test_client_cannot_send_prices_only_levels(client):
    """An unknown price level is a validation error — prices themselves
    are never accepted from the client (only the audited override)."""
    cat = build_catalog(client)
    response = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": cat["store"]["id"],
            "items": [
                {
                    "product_id": cat["product"]["id"],
                    "quantity": 1,
                    "price_level": "gratuit",
                }
            ],
        },
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_invalid_price_ordering_rejected_with_422(client):
    store = client.post("/api/v1/stores", json={"name": "B"}).json()
    response = client.post(
        "/api/v1/products",
        json={
            "store_id": store["id"],
            "name": "Produit incohérent",
            "cost_price": "10.00",
            "price_detail": "20.00",
            "price_gros": "25.00",
            "price_super_gros": "15.00",
        },
        headers=PIN_HEADER,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_price_levels"


def test_cost_price_required_at_creation(client):
    store = client.post("/api/v1/stores", json={"name": "B"}).json()
    response = client.post(
        "/api/v1/products",
        json={
            "store_id": store["id"],
            "name": "Produit sans coût",
            "price_detail": "20.00",
            "price_gros": "18.00",
            "price_super_gros": "15.00",
        },
        headers=PIN_HEADER,
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_oversell_rejected_with_409_and_no_partial_commit(client):
    cat = build_catalog(client)
    response = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": cat["store"]["id"],
            "items": [{"product_id": cat["product"]["id"], "quantity": 51}],
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "insufficient_stock"
    after = client.get(f"/api/v1/products/{cat['product']['id']}").json()
    assert after["stock_quantity"] == 50
    assert (
        client.get("/api/v1/sales", params={"store_id": cat["store"]["id"]}).json()
        == []
    )


def test_sell_to_exactly_zero_allowed(client):
    cat = build_catalog(client)
    response = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": cat["store"]["id"],
            "items": [{"product_id": cat["product"]["id"], "quantity": 50}],
        },
    )
    assert response.status_code == 201
    after = client.get(f"/api/v1/products/{cat['product']['id']}").json()
    assert after["stock_quantity"] == 0


def test_zero_and_negative_quantity_rejected_by_validation(client):
    cat = build_catalog(client)
    for bad_qty in (0, -3):
        response = client.post(
            "/api/v1/sales/checkout",
            json={
                "store_id": cat["store"]["id"],
                "items": [{"product_id": cat["product"]["id"], "quantity": bad_qty}],
            },
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"


def test_unknown_product_rejected(client):
    cat = build_catalog(client)
    response = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": cat["store"]["id"],
            "items": [
                {"product_id": "00000000-0000-0000-0000-000000000000", "quantity": 1}
            ],
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "product_unavailable"


def test_duplicate_customer_phone_rejected(client):
    cat = build_catalog(client)
    payload = {
        "store_id": cat["store"]["id"],
        "name": "Ali",
        "phone": "0550123456",
    }
    assert client.post("/api/v1/customers", json=payload).status_code == 201
    duplicate = client.post("/api/v1/customers", json=payload)
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "customer_phone_exists"


# ------------------------------------------------------------------- auth


def test_sensitive_actions_require_pin(client):
    store = client.post("/api/v1/stores", json={"name": "B"}).json()
    payload = {
        "store_id": store["id"],
        "name": "Produit",
        "cost_price": "10.00",
        "price_detail": "14.00",
        "price_gros": "13.00",
        "price_super_gros": "12.00",
    }
    no_pin = client.post("/api/v1/products", json=payload)
    assert no_pin.status_code == 401
    assert no_pin.json()["error"]["code"] == "invalid_pin"

    wrong_pin = client.post(
        "/api/v1/products", json=payload, headers={"X-Owner-Pin": "9999"}
    )
    assert wrong_pin.status_code == 401

    with_pin = client.post("/api/v1/products", json=payload, headers=PIN_HEADER)
    assert with_pin.status_code == 201
    assert with_pin.json()["cost_price"] == "10.00"  # owner view includes cost

    # Customer deletion is PIN-gated too.
    customer = client.post(
        "/api/v1/customers",
        json={"store_id": store["id"], "name": "Ali", "phone": "0550"},
    ).json()
    assert client.delete(f"/api/v1/customers/{customer['id']}").status_code == 401
    assert (
        client.delete(
            f"/api/v1/customers/{customer['id']}", headers=PIN_HEADER
        ).status_code
        == 204
    )


def test_pin_verify_endpoint(client):
    ok = client.post("/api/v1/auth/verify", json={"pin": PIN})
    assert ok.status_code == 200 and ok.json()["valid"] is True

    bad = client.post("/api/v1/auth/verify", json={"pin": "0000"})
    assert bad.status_code == 401
    assert bad.json()["error"]["code"] == "invalid_pin"


def test_statistics_require_pin(client):
    cat = build_catalog(client)
    for path, params in [
        ("summary", {"date_from": "2026-01-01", "date_to": "2026-01-31"}),
        ("overview", {}),
        (f"products/{cat['product']['id']}", {}),
        ("associations", {"date_from": "2026-01-01", "date_to": "2026-01-31"}),
        ("top-customers", {"date_from": "2026-01-01", "date_to": "2026-01-31"}),
    ]:
        response = client.get(
            f"/api/v1/statistics/{path}",
            params={"store_id": cat["store"]["id"], **params},
        )
        assert response.status_code == 401, path


def test_statistics_new_endpoints_shape(client):
    cat = build_catalog(client)
    store_id, product = cat["store"]["id"], cat["product"]
    client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": store_id,
            "items": [{"product_id": product["id"], "quantity": 2}],
        },
    )

    overview = client.get(
        "/api/v1/statistics/overview",
        params={"store_id": store_id},
        headers=PIN_HEADER,
    ).json()
    periods = {p["period"]: p for p in overview["periods"]}
    assert set(periods) == {"today", "this_week", "this_month", "this_year"}
    assert Decimal(periods["today"]["current"]["revenue"]) == Decimal("80.00")

    per_product = client.get(
        f"/api/v1/statistics/products/{product['id']}",
        params={"store_id": store_id},
        headers=PIN_HEADER,
    ).json()
    all_time = next(p for p in per_product["periods"] if p["period"] == "all_time")
    assert all_time["units_sold"] == 2
    assert Decimal(all_time["profit"]) == Decimal("30.00")

    assoc = client.get(
        "/api/v1/statistics/associations",
        params={
            "store_id": store_id,
            "date_from": "2020-01-01",
            "date_to": "2030-01-01",
            "min_support": 0.5,
            "min_confidence": 0.5,
        },
        headers=PIN_HEADER,
    ).json()
    assert assoc["basket_count"] == 1
    assert assoc["itemsets"][0]["products"][0]["name"] == "Eau minérale 1.5L"


# ------------------------------------------------------------------ docs


def test_swagger_docs_and_openapi_list_all_endpoints(client):
    assert client.get("/docs").status_code == 200
    paths = client.get("/openapi.json").json()["paths"]
    for expected in [
        "/api/v1/auth/verify",
        "/api/v1/stores",
        "/api/v1/categories",
        "/api/v1/products",
        "/api/v1/products/by-barcode/{barcode}",
        "/api/v1/products/{product_id}/image",
        "/api/v1/customers",
        "/api/v1/customers/{customer_id}",
        "/api/v1/sales/checkout",
        "/api/v1/sales/{sale_id}/payments",
        "/api/v1/sales/{sale_id}/receipt",
        "/api/v1/statistics/summary",
        "/api/v1/statistics/top-products",
        "/api/v1/statistics/overview",
        "/api/v1/statistics/products/{product_id}",
        "/api/v1/statistics/top-customers",
        "/api/v1/statistics/customers/{customer_id}",
        "/api/v1/statistics/associations",
        "/api/v1/alerts",
        "/api/v1/settings",
    ]:
        assert expected in paths, f"missing {expected}"
    # The legacy tier endpoints are gone.
    assert not any(p.startswith("/api/v1/price-tiers") for p in paths)
