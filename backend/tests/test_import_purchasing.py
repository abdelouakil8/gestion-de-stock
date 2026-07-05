"""Tests for Phase 10 & 11: invoicing, discounts, payment methods,
CSV import, suppliers, and purchasing."""

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
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    monkeypatch.setattr(settings, "pin_hash", hash_pin(PIN))
    app.dependency_overrides[deps.get_db] = lambda: session
    with TestClient(app, raise_server_exceptions=False) as tc:
        yield tc
    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


def _catalog(client) -> dict:
    store = client.post("/api/v1/stores", json={"name": "TestStore"}).json()
    product = client.post(
        "/api/v1/products",
        json={
            "store_id": store["id"],
            "name": "Widget",
            "barcode": "1234567890",
            "cost_price": "5.00",
            "price_detail": "10.00",
            "price_gros": "8.00",
            "price_super_gros": "6.00",
            "stock_quantity": 100,
        },
        headers=PIN_HEADER,
    ).json()
    return {"store": store, "product": product}


# ────────────────────── Invoice numbering ──────────────────────


class TestInvoiceNumbering:
    def test_first_sale_gets_invoice_1(self, client):
        cat = _catalog(client)
        sale = client.post(
            "/api/v1/sales/checkout",
            json={
                "store_id": cat["store"]["id"],
                "items": [{"product_id": cat["product"]["id"], "quantity": 1}],
            },
        ).json()
        assert sale["invoice_number"] == 1

    def test_sequential_gapless(self, client):
        cat = _catalog(client)
        for expected in (1, 2, 3):
            sale = client.post(
                "/api/v1/sales/checkout",
                json={
                    "store_id": cat["store"]["id"],
                    "items": [{"product_id": cat["product"]["id"], "quantity": 1}],
                },
            ).json()
            assert sale["invoice_number"] == expected

    def test_receipt_uses_invoice_number(self, client):
        cat = _catalog(client)
        sale = client.post(
            "/api/v1/sales/checkout",
            json={
                "store_id": cat["store"]["id"],
                "items": [{"product_id": cat["product"]["id"], "quantity": 1}],
            },
        ).json()
        receipt = client.get(f"/api/v1/sales/{sale['id']}/receipt")
        assert receipt.status_code == 200
        assert b"%PDF" in receipt.content


# ────────────────────── Discounts ──────────────────────


class TestDiscounts:
    def test_discount_applied_to_line_total(self, client):
        cat = _catalog(client)
        sale = client.post(
            "/api/v1/sales/checkout",
            json={
                "store_id": cat["store"]["id"],
                "items": [
                    {
                        "product_id": cat["product"]["id"],
                        "quantity": 5,
                        "discount_amount": "10.00",
                    }
                ],
            },
        ).json()
        # 5 × 10.00 - 10.00 = 40.00
        assert sale["total_amount"] == "40.00"
        assert sale["items"][0]["discount_amount"] == "10.00"

    def test_discount_floor_check(self, client):
        """Discount that pushes effective unit below floor is rejected."""
        cat = _catalog(client)
        # floor = price_super_gros = 6.00; qty=2 → max discount = (10-6)*2 = 8
        resp = client.post(
            "/api/v1/sales/checkout",
            json={
                "store_id": cat["store"]["id"],
                "items": [
                    {
                        "product_id": cat["product"]["id"],
                        "quantity": 2,
                        "discount_amount": "8.01",
                    }
                ],
            },
        )
        assert resp.status_code == 409

    def test_discount_at_floor_allowed(self, client):
        cat = _catalog(client)
        resp = client.post(
            "/api/v1/sales/checkout",
            json={
                "store_id": cat["store"]["id"],
                "items": [
                    {
                        "product_id": cat["product"]["id"],
                        "quantity": 2,
                        "discount_amount": "8.00",
                    }
                ],
            },
        )
        assert resp.status_code == 201
        assert resp.json()["total_amount"] == "12.00"  # 2×10 - 8

    def test_stats_include_total_discounts(self, client):
        cat = _catalog(client)
        client.post(
            "/api/v1/sales/checkout",
            json={
                "store_id": cat["store"]["id"],
                "items": [
                    {
                        "product_id": cat["product"]["id"],
                        "quantity": 2,
                        "discount_amount": "5.00",
                    }
                ],
            },
        )
        stats = client.get(
            "/api/v1/statistics/summary",
            params={
                "store_id": cat["store"]["id"],
                "date_from": "2020-01-01",
                "date_to": "2030-01-01",
            },
            headers=PIN_HEADER,
        ).json()
        assert Decimal(stats["total_discounts"]) == Decimal("5.00")


# ────────────────────── Payment method ──────────────────────


class TestPaymentMethod:
    def test_payment_method_persisted(self, client):
        cat = _catalog(client)
        sale = client.post(
            "/api/v1/sales/checkout",
            json={
                "store_id": cat["store"]["id"],
                "items": [{"product_id": cat["product"]["id"], "quantity": 1}],
                "payment": {"mode": "full", "payment_method": "card"},
            },
        ).json()
        assert sale["payments"][0]["payment_method"] == "card"

    def test_payment_method_breakdown(self, client):
        cat = _catalog(client)
        for method in ("cash", "card", "card"):
            client.post(
                "/api/v1/sales/checkout",
                json={
                    "store_id": cat["store"]["id"],
                    "items": [{"product_id": cat["product"]["id"], "quantity": 1}],
                    "payment": {"mode": "full", "payment_method": method},
                },
            )
        breakdown = client.get(
            "/api/v1/statistics/payment-methods",
            params={
                "store_id": cat["store"]["id"],
                "date_from": "2020-01-01",
                "date_to": "2030-01-01",
            },
            headers=PIN_HEADER,
        ).json()
        by_method = {r["payment_method"]: r for r in breakdown}
        assert by_method["card"]["count"] == 2
        assert by_method["cash"]["count"] == 1


# ────────────────────── CSV Import ──────────────────────


class TestCSVImport:
    def test_import_creates_products(self, client):
        store = client.post("/api/v1/stores", json={"name": "ImportStore"}).json()
        csv = (
            "name;barcode;price_detail;price_gros;price_super_gros;"
            "cost_price;stock_quantity\n"
            "Produit A;AAA001;10.00;8.00;6.00;4.00;100\n"
            "Produit B;BBB002;20.00;15.00;12.00;8.00;50\n"
        )
        resp = client.post(
            "/api/v1/products/import",
            params={"store_id": store["id"]},
            files={"file": ("test.csv", csv.encode(), "text/csv")},
            headers=PIN_HEADER,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["created"] == 2
        assert data["updated"] == 0
        assert data["errors"] == []

    def test_import_updates_by_barcode(self, client):
        store = client.post("/api/v1/stores", json={"name": "ImportStore2"}).json()
        csv1 = (
            "name;barcode;price_detail;price_gros;price_super_gros;"
            "cost_price;stock_quantity\n"
            "Old;UPD01;10.00;8.00;6.00;4.00;10\n"
        )
        client.post(
            "/api/v1/products/import",
            params={"store_id": store["id"]},
            files={"file": ("test.csv", csv1.encode(), "text/csv")},
            headers=PIN_HEADER,
        )
        csv2 = (
            "name;barcode;price_detail;price_gros;price_super_gros;"
            "cost_price;stock_quantity\n"
            "New;UPD01;12.00;10.00;8.00;5.00;20\n"
        )
        resp = client.post(
            "/api/v1/products/import",
            params={"store_id": store["id"]},
            files={"file": ("test.csv", csv2.encode(), "text/csv")},
            headers=PIN_HEADER,
        )
        data = resp.json()
        assert data["updated"] == 1
        assert data["created"] == 0

    def test_import_row_errors_do_not_abort(self, client):
        store = client.post("/api/v1/stores", json={"name": "ImportStore3"}).json()
        csv = (
            "name;barcode;price_detail;price_gros;price_super_gros;"
            "cost_price;stock_quantity\n"
            "Good;G01;10.00;8.00;6.00;4.00;10\n"
            ";BAD;abc;8.00;6.00;4.00;10\n"
            "Also Good;G02;20.00;15.00;12.00;8.00;5\n"
        )
        resp = client.post(
            "/api/v1/products/import",
            params={"store_id": store["id"]},
            files={"file": ("test.csv", csv.encode(), "text/csv")},
            headers=PIN_HEADER,
        )
        data = resp.json()
        assert data["created"] == 2
        assert len(data["errors"]) == 1
        assert data["errors"][0]["row"] == 3


# ────────────────────── Suppliers ──────────────────────


class TestSuppliers:
    def test_create_and_list(self, client):
        store = client.post("/api/v1/stores", json={"name": "SupStore"}).json()
        resp = client.post(
            "/api/v1/suppliers",
            json={
                "store_id": store["id"],
                "name": "Fournisseur A",
                "phone": "0555123456",
            },
            headers=PIN_HEADER,
        )
        assert resp.status_code == 201
        assert resp.json()["name"] == "Fournisseur A"

        listed = client.get(
            "/api/v1/suppliers", params={"store_id": store["id"]}
        ).json()
        assert len(listed) == 1

    def test_duplicate_phone_rejected(self, client):
        store = client.post("/api/v1/stores", json={"name": "SupStore2"}).json()
        payload = {
            "store_id": store["id"],
            "name": "Fournisseur A",
            "phone": "0555123456",
        }
        client.post("/api/v1/suppliers", json=payload, headers=PIN_HEADER)
        resp = client.post("/api/v1/suppliers", json=payload, headers=PIN_HEADER)
        assert resp.status_code == 409


# ────────────────────── Purchasing ──────────────────────


class TestPurchasing:
    def test_receive_stock_increments(self, client):
        cat = _catalog(client)
        supplier = client.post(
            "/api/v1/suppliers",
            json={
                "store_id": cat["store"]["id"],
                "name": "Sup",
                "phone": "0550001111",
            },
            headers=PIN_HEADER,
        ).json()

        resp = client.post(
            "/api/v1/purchase-orders",
            json={
                "store_id": cat["store"]["id"],
                "supplier_id": supplier["id"],
                "items": [
                    {
                        "product_id": cat["product"]["id"],
                        "quantity": 20,
                        "unit_cost": "5.00",
                    }
                ],
                "payment_amount": "50.00",
                "payment_method": "cash",
            },
            headers=PIN_HEADER,
        )
        assert resp.status_code == 201
        order = resp.json()
        assert order["total_amount"] == "100.00"
        assert order["paid_amount"] == "50.00"

        updated = client.get(f"/api/v1/products/{cat['product']['id']}").json()
        assert updated["stock_quantity"] == 120  # 100 + 20

    def test_supplier_payment_recorded(self, client):
        cat = _catalog(client)
        supplier = client.post(
            "/api/v1/suppliers",
            json={
                "store_id": cat["store"]["id"],
                "name": "Sup2",
                "phone": "0550002222",
            },
            headers=PIN_HEADER,
        ).json()

        order = client.post(
            "/api/v1/purchase-orders",
            json={
                "store_id": cat["store"]["id"],
                "supplier_id": supplier["id"],
                "items": [
                    {
                        "product_id": cat["product"]["id"],
                        "quantity": 10,
                        "unit_cost": "5.00",
                    }
                ],
            },
            headers=PIN_HEADER,
        ).json()

        resp = client.post(
            f"/api/v1/purchase-orders/{order['id']}/payments",
            json={"amount": "30.00", "payment_method": "card"},
            headers=PIN_HEADER,
        )
        assert resp.status_code == 201
        assert resp.json()["paid_amount"] == "30.00"
