"""Multi-user roles + session-token auth (Phase 17).

Covers: the login list lazily seeding the owner from the legacy PIN, PIN login
issuing a session token, the three role floors (cashier < manager < owner)
failing closed, the last-owner guard, and per-user sale ownership. The legacy
``X-Owner-Pin`` bridge is used for owner setup calls (proving it still maps to
owner).
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.core import sessions
from app.core.config import settings
from app.core.security import hash_pin
from app.main import app
from app.models import Base

PIN = "1234"
OWNER_HEADER = {"X-Owner-Pin": PIN}


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
    sessions.clear()
    app.dependency_overrides[deps.get_db] = lambda: session
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    sessions.clear()
    session.close()
    engine.dispose()


def _store(client) -> str:
    return client.post("/api/v1/stores", json={"name": "Boutique"}).json()["id"]


def _product(client, store_id: str) -> dict:
    return client.post(
        "/api/v1/products",
        json={
            "store_id": store_id,
            "name": "Eau 1.5L",
            "cost_price": "25.00",
            "price_detail": "40.00",
            "price_gros": "37.50",
            "price_super_gros": "30.00",
            "stock_quantity": 50,
        },
        headers=OWNER_HEADER,
    ).json()


def _login(client, user_id: str, pin: str) -> str:
    r = client.post("/api/v1/auth/login", json={"user_id": user_id, "pin": pin})
    assert r.status_code == 200, r.text
    return r.json()["token"]


# --------------------------------------------------- login + bootstrap


def test_login_list_seeds_owner_and_login_issues_token(client):
    _store(client)
    # The public login list lazily materialises the owner from the legacy PIN.
    users = client.get("/api/v1/auth/users").json()
    assert len(users) == 1
    assert users[0]["role"] == "owner"
    assert "pin_hash" not in users[0]

    owner_id = users[0]["id"]
    # Wrong PIN is rejected.
    assert (
        client.post(
            "/api/v1/auth/login", json={"user_id": owner_id, "pin": "0000"}
        ).status_code
        == 401
    )
    token = _login(client, owner_id, PIN)

    # The session token authorises an owner-only route (settings update).
    r = client.put(
        "/api/v1/settings",
        params={"store_id": _store_id_of(client)},
        json={"shop_name": "Chez X"},
        headers={"X-Session-Token": token},
    )
    assert r.status_code == 200, r.text


def _store_id_of(client) -> str:
    return client.get("/api/v1/stores").json()[0]["id"]


# --------------------------------------------------------- role floors


def test_role_floors_fail_closed(client):
    store_id = _store(client)
    # Seed owner + create a cashier and a manager (owner action via bridge).
    owner_id = client.get("/api/v1/auth/users").json()[0]["id"]
    cashier = client.post(
        "/api/v1/users",
        json={
            "store_id": store_id,
            "name": "Caissier",
            "role": "cashier",
            "pin": "1111",
        },
        headers=OWNER_HEADER,
    ).json()
    manager = client.post(
        "/api/v1/users",
        json={"store_id": store_id, "name": "Gérant", "role": "manager", "pin": "2222"},
        headers=OWNER_HEADER,
    ).json()

    product = _product(client, store_id)
    ctok = _login(client, cashier["id"], "1111")
    mtok = _login(client, manager["id"], "2222")
    otok = _login(client, owner_id, PIN)

    # Cashier CAN checkout (cashier floor)...
    r = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": store_id,
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
        headers={"X-Session-Token": ctok},
    )
    assert r.status_code == 201, r.text

    # ...but CANNOT create a product (manager floor) -> 403.
    assert (
        client.post(
            "/api/v1/products",
            json={
                "store_id": store_id,
                "name": "X",
                "cost_price": "1.00",
                "price_detail": "2.00",
                "price_gros": "2.00",
                "price_super_gros": "2.00",
                "stock_quantity": 1,
            },
            headers={"X-Session-Token": ctok},
        ).status_code
        == 403
    )

    # Manager CAN create a product...
    assert (
        client.post(
            "/api/v1/products",
            json={
                "store_id": store_id,
                "name": "Y",
                "cost_price": "1.00",
                "price_detail": "2.00",
                "price_gros": "2.00",
                "price_super_gros": "2.00",
                "stock_quantity": 1,
            },
            headers={"X-Session-Token": mtok},
        ).status_code
        == 201
    )
    # ...but CANNOT update settings (owner floor) -> 403.
    assert (
        client.put(
            "/api/v1/settings",
            params={"store_id": store_id},
            json={"shop_name": "Z"},
            headers={"X-Session-Token": mtok},
        ).status_code
        == 403
    )

    # Owner can do the owner action.
    assert (
        client.put(
            "/api/v1/settings",
            params={"store_id": store_id},
            json={"shop_name": "Z"},
            headers={"X-Session-Token": otok},
        ).status_code
        == 200
    )

    # No token at all on a manager route -> 401 (fails closed once users exist).
    assert (
        client.post(
            "/api/v1/products",
            json={
                "store_id": store_id,
                "name": "N",
                "cost_price": "1.00",
                "price_detail": "2.00",
                "price_gros": "2.00",
                "price_super_gros": "2.00",
                "stock_quantity": 1,
            },
        ).status_code
        == 401
    )


# ------------------------------------------------------ last-owner guard


def test_last_owner_cannot_be_demoted_or_deactivated(client):
    _store(client)
    owner_id = client.get("/api/v1/auth/users").json()[0]["id"]

    demote = client.patch(
        f"/api/v1/users/{owner_id}",
        json={"role": "cashier"},
        headers=OWNER_HEADER,
    )
    assert demote.status_code == 409
    assert demote.json()["error"]["code"] == "last_owner"

    deactivate = client.delete(f"/api/v1/users/{owner_id}", headers=OWNER_HEADER)
    assert deactivate.status_code == 409


# ------------------------------------------------- per-user sale ownership


def test_checkout_records_ringing_user(client):
    store_id = _store(client)
    cashier = client.post(
        "/api/v1/users",
        json={
            "store_id": store_id,
            "name": "Caissier",
            "role": "cashier",
            "pin": "1111",
        },
        headers=OWNER_HEADER,
    ).json()
    product = _product(client, store_id)
    ctok = _login(client, cashier["id"], "1111")

    sale = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": store_id,
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
        headers={"X-Session-Token": ctok},
    ).json()
    assert sale["created_by_user_id"] == cashier["id"]

    # The "own sales" filter returns it.
    own = client.get(
        "/api/v1/sales",
        params={"store_id": store_id, "created_by_user_id": cashier["id"]},
    ).json()
    assert len(own) == 1 and own[0]["id"] == sale["id"]


def test_checkout_open_mode_when_no_users(client):
    """With no named users, checkout stays public (legacy behaviour)."""
    store_id = _store(client)
    product = _product(client, store_id)
    r = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": store_id,
            "items": [{"product_id": product["id"], "quantity": 1}],
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["created_by_user_id"] is None
