"""Barcode label sheet generation (Phase 20)."""

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


def _product(client, store_id, name, barcode):
    return client.post(
        "/api/v1/products",
        json={
            "store_id": store_id,
            "name": name,
            "barcode": barcode,
            "cost_price": "25.00",
            "price_detail": "40.00",
            "price_gros": "37.50",
            "price_super_gros": "30.00",
            "stock_quantity": 10,
        },
        headers=OWNER,
    ).json()


def test_generate_labels_renders_pdf(client):
    store = client.post("/api/v1/stores", json={"name": "B"}).json()
    ean = _product(client, store["id"], "Eau", "6130000000015")
    code128 = _product(client, store["id"], "Riz", "ABC-123")

    r = client.post(
        "/api/v1/products/labels/generate",
        params={"store_id": store["id"]},
        json={
            "product_ids": [ean["id"], code128["id"]],
            "label_config": {
                "size": "58x40",
                "barcode_type": "ean13",
                "copies": 3,
                "show_store": True,
            },
        },
        headers=OWNER,
    )
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"
    assert len(r.content) > 1000


def test_generate_labels_requires_manager(client):
    store = client.post("/api/v1/stores", json={"name": "B"}).json()
    p = _product(client, store["id"], "Eau", "6130000000015")
    r = client.post(
        "/api/v1/products/labels/generate",
        params={"store_id": store["id"]},
        json={"product_ids": [p["id"]], "label_config": {}},
    )
    assert r.status_code == 401
