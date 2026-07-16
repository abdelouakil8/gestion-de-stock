"""End-to-end tests for the Phase 15/16 surface:

- manual stock adjustment (POST /products/{id}/adjust-stock) + the adjustment
  movement it writes;
- the store-wide movements ledger (GET /products/movements);
- outstanding credits list + PDF (GET /sales/outstanding[.pdf]);
- the daily cash closing (GET /sales/day-summary, POST /sales/close-day,
  GET /sales/close-day.pdf) with the once-per-day guard;
- the end-of-day report PDF (GET /statistics/daily-report.pdf).

All owner endpoints are exercised WITH the PIN header and one WITHOUT, to pin
down the auth boundary.
"""

from datetime import date

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


def _catalog(client) -> dict:
    store = client.post("/api/v1/stores", json={"name": "Boutique"}).json()
    product = client.post(
        "/api/v1/products",
        json={
            "store_id": store["id"],
            "name": "Eau 1.5L",
            "barcode": "6130000000015",
            "cost_price": "25.00",
            "price_detail": "40.00",
            "price_gros": "37.50",
            "price_super_gros": "30.00",
            "stock_quantity": 50,
        },
        headers=PIN_HEADER,
    ).json()
    return {"store_id": store["id"], "product": product}


# --------------------------------------------------- Feature 1: adjustment


def test_adjust_stock_sets_absolute_quantity_and_writes_movement(client):
    cat = _catalog(client)
    store_id, product = cat["store_id"], cat["product"]

    r = client.post(
        f"/api/v1/products/{product['id']}/adjust-stock",
        json={"new_quantity": 42, "reason": "inventaire", "note": "recomptage"},
        headers=PIN_HEADER,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["old_quantity"] == 50
    assert body["new_quantity"] == 42
    assert body["delta"] == -8

    # Stock really changed.
    listed = client.get("/api/v1/products", params={"store_id": store_id}).json()
    assert listed["items"][0]["stock_quantity"] == 42

    # An adjustment movement was recorded with the reason + note.
    page = client.get(
        f"/api/v1/products/{product['id']}/movements",
        params={"store_id": store_id},
        headers=PIN_HEADER,
    ).json()
    latest = page["items"][0]
    assert latest["movement_type"] == "adjustment"
    assert latest["quantity_delta"] == -8
    assert latest["quantity_after"] == 42
    assert latest["reason"] == "inventaire"
    assert latest["note"] == "recomptage"


def test_adjust_stock_requires_pin(client):
    cat = _catalog(client)
    r = client.post(
        f"/api/v1/products/{cat['product']['id']}/adjust-stock",
        json={"new_quantity": 10, "reason": "perte"},
    )
    assert r.status_code == 401


def test_adjust_stock_rejects_negative_quantity(client):
    cat = _catalog(client)
    r = client.post(
        f"/api/v1/products/{cat['product']['id']}/adjust-stock",
        json={"new_quantity": -1, "reason": "casse"},
        headers=PIN_HEADER,
    )
    assert r.status_code == 422  # schema ge=0


# ------------------------------------------------ Feature 2: movements log


def test_global_movements_join_product_and_filter_by_type(client):
    cat = _catalog(client)
    store_id, product = cat["store_id"], cat["product"]

    # One sale (movement type "sale") + one adjustment.
    client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": store_id,
            "items": [{"product_id": product["id"], "quantity": 2}],
        },
    )
    client.post(
        f"/api/v1/products/{product['id']}/adjust-stock",
        json={"new_quantity": 60, "reason": "correction"},
        headers=PIN_HEADER,
    )

    page = client.get(
        "/api/v1/products/movements",
        params={"store_id": store_id},
        headers=PIN_HEADER,
    ).json()
    assert page["total"] == 2
    # Product name is joined in server-side (no N+1 on the client).
    assert all(item["product_name"] == "Eau 1.5L" for item in page["items"])

    # Type filter narrows to adjustments only.
    adj = client.get(
        "/api/v1/products/movements",
        params={"store_id": store_id, "type": "adjustment"},
        headers=PIN_HEADER,
    ).json()
    assert adj["total"] == 1
    assert adj["items"][0]["movement_type"] == "adjustment"

    # The literal /movements path wins over /{product_id} — no 422.
    assert (
        client.get(
            "/api/v1/products/movements",
            params={"store_id": store_id},
            headers=PIN_HEADER,
        ).status_code
        == 200
    )


def test_movements_requires_pin(client):
    cat = _catalog(client)
    r = client.get("/api/v1/products/movements", params={"store_id": cat["store_id"]})
    assert r.status_code == 401


# ------------------------------------------------- Feature 3: outstanding


def test_outstanding_lists_credit_sales_and_exports_pdf(client):
    cat = _catalog(client)
    store_id, product = cat["store_id"], cat["product"]
    customer = client.post(
        "/api/v1/customers",
        json={"store_id": store_id, "name": "Ali", "phone": "0555000000"},
    ).json()

    # A partial (credit) sale: total 80.00, paid 30.00.
    client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": store_id,
            "items": [{"product_id": product["id"], "quantity": 2}],
            "payment": {
                "mode": "partial",
                "amount_paid": "30.00",
                "customer_id": customer["id"],
            },
        },
    )

    out = client.get(
        "/api/v1/sales/outstanding",
        params={"store_id": store_id},
        headers=PIN_HEADER,
    ).json()
    assert len(out) == 1
    assert out[0]["balance"] == "50.00"
    assert out[0]["customer_name"] == "Ali"

    pdf = client.get(
        "/api/v1/sales/outstanding.pdf",
        params={"store_id": store_id},
        headers=PIN_HEADER,
    )
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"


# ------------------------------------------------ Feature 4: day closing


def test_close_day_computes_gap_and_is_once_per_day(client):
    cat = _catalog(client)
    store_id, product = cat["store_id"], cat["product"]
    today = date.today().isoformat()

    # Two fully-paid cash sales today: 2×40 + 1×40 = 120.00 cash in.
    client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": store_id,
            "items": [{"product_id": product["id"], "quantity": 2}],
        },
    )
    client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": store_id,
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
    )

    summary = client.get(
        "/api/v1/sales/day-summary",
        params={"store_id": store_id, "day": today},
        headers=PIN_HEADER,
    ).json()
    assert summary["sales_count"] == 2
    assert summary["cash_total"] == "120.00"
    assert summary["expected_cash"] == "120.00"
    assert summary["already_closed"] is False

    # Counted 118.00 -> gap -2.00.
    closed = client.post(
        "/api/v1/sales/close-day",
        json={
            "store_id": store_id,
            "date": today,
            "physical_cash_count": "118.00",
            "notes": "petit manque",
        },
        headers=PIN_HEADER,
    )
    assert closed.status_code == 201, closed.text
    body = closed.json()
    assert body["expected_cash"] == "120.00"
    assert body["gap"] == "-2.00"

    # The day now reports closed, and a second close is rejected.
    again = client.get(
        "/api/v1/sales/day-summary",
        params={"store_id": store_id, "day": today},
        headers=PIN_HEADER,
    ).json()
    assert again["already_closed"] is True

    dup = client.post(
        "/api/v1/sales/close-day",
        json={"store_id": store_id, "date": today, "physical_cash_count": "120.00"},
        headers=PIN_HEADER,
    )
    assert dup.status_code == 409
    assert dup.json()["error"]["code"] == "day_already_closed"

    # The closing PDF renders.
    pdf = client.get(
        "/api/v1/sales/close-day.pdf",
        params={
            "store_id": store_id,
            "day": today,
            "physical_cash_count": "118.00",
        },
        headers=PIN_HEADER,
    )
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"


# ---------------------------------------------- Feature 5: daily report


def test_daily_report_pdf_renders(client):
    cat = _catalog(client)
    store_id, product = cat["store_id"], cat["product"]
    client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": store_id,
            "items": [{"product_id": product["id"], "quantity": 3}],
        },
    )
    pdf = client.get(
        "/api/v1/statistics/daily-report.pdf",
        params={"store_id": store_id, "date": date.today().isoformat()},
        headers=PIN_HEADER,
    )
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"

    # Owner-gated.
    assert (
        client.get(
            "/api/v1/statistics/daily-report.pdf",
            params={"store_id": store_id, "date": date.today().isoformat()},
        ).status_code
        == 401
    )
