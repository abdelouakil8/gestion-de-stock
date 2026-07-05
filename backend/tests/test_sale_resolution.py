"""Customer Attach + Guest Sale: the two new post-checkout mutations and the
extended sales listing, all exercised over HTTP.

A finalized sale is immutable except payments; the ONLY ways its customer
state may change afterwards are assign_customer (walk-in/anonymous -> named)
and confirm_guest (walk-in -> intentionally anonymous, idempotent). Neither
ever rewrites an existing customer_id. This file plays the same hostile UI as
test_api.py: assigning a foreign/deleted customer, double-assigning, confirming
a sale that already has a customer — each must return a structured French error.
"""

from datetime import datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.core.config import settings
from app.core.security import hash_pin
from app.main import app
from app.models import Base, Sale

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
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


def _session() -> Session:
    """The single shared session the fixture handed to the app.

    Needed to backdate Sale.created_at directly — the checkout API has no way
    to set it, so the date-window filter can only be exercised this way.
    """
    return app.dependency_overrides[deps.get_db]()


# ---------------------------------------------------------------- builders


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
            "stock_quantity": 500,
        },
        headers=PIN_HEADER,
    ).json()
    return {"store": store, "category": category, "product": product}


def make_customer(client, store_id, name="Ali Benali", phone="0550123456") -> dict:
    return client.post(
        "/api/v1/customers",
        json={"store_id": store_id, "name": name, "phone": phone},
    ).json()


def guest_sale(client, store_id, product_id, quantity=1) -> dict:
    """Checkout with no customer, full payment -> a walk-in guest sale."""
    resp = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": store_id,
            "items": [{"product_id": product_id, "quantity": quantity}],
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["customer_id"] is None
    assert body["guest_confirmed_at"] is None
    return body


def assigned_sale(client, store_id, product_id, customer_id, quantity=1) -> dict:
    """Checkout then attach a customer -> an assigned sale."""
    sale = guest_sale(client, store_id, product_id, quantity=quantity)
    resp = client.post(
        f"/api/v1/sales/{sale['id']}/customer", json={"customer_id": customer_id}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------- assign customer


def test_assign_customer_to_guest_sale(client):
    cat = build_catalog(client)
    store_id, product = cat["store"]["id"], cat["product"]
    customer = make_customer(client, store_id)
    sale = guest_sale(client, store_id, product["id"], quantity=2)  # 80.00 full

    resp = client.post(
        f"/api/v1/sales/{sale['id']}/customer",
        json={"customer_id": customer["id"]},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["customer_id"] == customer["id"]
    assert body["customer_name"] == "Ali Benali"
    assert body["customer_phone"] == "0550123456"
    assert body["guest_confirmed_at"] is None  # assign never confirms guest


def test_assign_to_already_assigned_sale_is_409(client):
    cat = build_catalog(client)
    store_id, product = cat["store"]["id"], cat["product"]
    first = make_customer(client, store_id, name="Ali", phone="0550000001")
    second = make_customer(client, store_id, name="Brahim", phone="0550000002")
    sale = assigned_sale(client, store_id, product["id"], first["id"])

    resp = client.post(
        f"/api/v1/sales/{sale['id']}/customer",
        json={"customer_id": second["id"]},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "sale_customer_already_set"

    # The original assignment is untouched (never rewritten).
    fetched = client.get(f"/api/v1/sales/{sale['id']}").json()
    assert fetched["customer_id"] == first["id"]


def test_assign_customer_from_another_store_is_404(client):
    cat = build_catalog(client)
    store_id, product = cat["store"]["id"], cat["product"]
    other = client.post("/api/v1/stores", json={"name": "Autre boutique"}).json()
    foreign = make_customer(client, other["id"], name="Étranger", phone="0660000000")
    sale = guest_sale(client, store_id, product["id"])

    resp = client.post(
        f"/api/v1/sales/{sale['id']}/customer",
        json={"customer_id": foreign["id"]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_assign_customer_to_unknown_sale_is_404(client):
    cat = build_catalog(client)
    store_id = cat["store"]["id"]
    customer = make_customer(client, store_id)

    resp = client.post(
        "/api/v1/sales/00000000-0000-0000-0000-000000000000/customer",
        json={"customer_id": customer["id"]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_assign_soft_deleted_customer_is_404(client):
    cat = build_catalog(client)
    store_id, product = cat["store"]["id"], cat["product"]
    customer = make_customer(client, store_id)
    sale = guest_sale(client, store_id, product["id"])

    archived = client.delete(f"/api/v1/customers/{customer['id']}", headers=PIN_HEADER)
    assert archived.status_code == 204

    resp = client.post(
        f"/api/v1/sales/{sale['id']}/customer",
        json={"customer_id": customer["id"]},
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def test_assign_customer_reflected_in_customer_aggregate(client):
    cat = build_catalog(client)
    store_id, product = cat["store"]["id"], cat["product"]
    customer = make_customer(client, store_id)
    sale = guest_sale(client, store_id, product["id"], quantity=3)  # 120.00

    assign = client.post(
        f"/api/v1/sales/{sale['id']}/customer",
        json={"customer_id": customer["id"]},
    )
    assert assign.status_code == 200

    stats = client.get(
        f"/api/v1/statistics/customers/{customer['id']}", headers=PIN_HEADER
    ).json()
    assert stats["sales_count"] == 1
    assert stats["total_revenue"] == sale["total_amount"] == "120.00"


# ------------------------------------------------------------- confirm guest


def test_confirm_guest_sets_timestamp(client):
    cat = build_catalog(client)
    store_id, product = cat["store"]["id"], cat["product"]
    sale = guest_sale(client, store_id, product["id"])

    resp = client.post(f"/api/v1/sales/{sale['id']}/confirm-guest")
    assert resp.status_code == 200
    body = resp.json()
    assert body["customer_id"] is None
    assert body["guest_confirmed_at"] is not None


def test_confirm_guest_is_idempotent(client):
    cat = build_catalog(client)
    store_id, product = cat["store"]["id"], cat["product"]
    sale = guest_sale(client, store_id, product["id"])

    first = client.post(f"/api/v1/sales/{sale['id']}/confirm-guest").json()
    second = client.post(f"/api/v1/sales/{sale['id']}/confirm-guest").json()
    assert first["guest_confirmed_at"] is not None
    # Same timestamp — the first confirmation is preserved, not overwritten.
    assert second["guest_confirmed_at"] == first["guest_confirmed_at"]


def test_confirm_guest_on_sale_with_customer_is_409(client):
    cat = build_catalog(client)
    store_id, product = cat["store"]["id"], cat["product"]
    customer = make_customer(client, store_id)
    sale = assigned_sale(client, store_id, product["id"], customer["id"])

    resp = client.post(f"/api/v1/sales/{sale['id']}/confirm-guest")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "sale_has_customer"


def test_confirm_guest_unknown_sale_is_404(client):
    build_catalog(client)
    resp = client.post(
        "/api/v1/sales/00000000-0000-0000-0000-000000000000/confirm-guest"
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


# -------------------------------------------------------------- extended list


def _order_by_created(client, store_id, product_id, count):
    """Create `count` guest sales with strictly increasing created_at.

    SQLite's server-side now() has only second resolution, so sales made in
    the same second tie; backdate to distinct minutes to make the DESC order
    deterministic. Returns the ids in creation order (oldest -> newest).
    """
    ids = [guest_sale(client, store_id, product_id)["id"] for _ in range(count)]
    session = _session()
    for i, sale_id in enumerate(ids):
        session.get(Sale, UUID(sale_id)).created_at = datetime(2026, 1, 1, 8, i, 0)
    session.commit()
    return ids


def test_list_sales_no_filter_returns_all_desc(client):
    cat = build_catalog(client)
    store_id, product = cat["store"]["id"], cat["product"]
    ids = _order_by_created(client, store_id, product["id"], 3)

    listed = client.get("/api/v1/sales", params={"store_id": store_id}).json()
    assert len(listed) == 3
    # Newest first: the last created sale leads.
    assert [s["id"] for s in listed] == list(reversed(ids))


def test_list_sales_filter_by_customer(client):
    cat = build_catalog(client)
    store_id, product = cat["store"]["id"], cat["product"]
    customer = make_customer(client, store_id)
    assigned = assigned_sale(client, store_id, product["id"], customer["id"])
    guest_sale(client, store_id, product["id"])  # unrelated walk-in

    listed = client.get(
        "/api/v1/sales",
        params={"store_id": store_id, "customer_id": customer["id"]},
    ).json()
    assert [s["id"] for s in listed] == [assigned["id"]]
    assert listed[0]["customer_name"] == "Ali Benali"
    assert listed[0]["customer_phone"] == "0550123456"


def test_list_sales_guest_filters(client):
    cat = build_catalog(client)
    store_id, product = cat["store"]["id"], cat["product"]
    customer = make_customer(client, store_id)

    pending = guest_sale(client, store_id, product["id"])  # NULL customer, unconfirmed
    confirmed_src = guest_sale(client, store_id, product["id"])
    client.post(f"/api/v1/sales/{confirmed_src['id']}/confirm-guest")
    assigned = assigned_sale(client, store_id, product["id"], customer["id"])

    def ids(guest):
        listed = client.get(
            "/api/v1/sales", params={"store_id": store_id, "guest": guest}
        ).json()
        return {s["id"] for s in listed}

    assert ids("pending") == {pending["id"]}
    assert ids("confirmed") == {confirmed_src["id"]}
    # any = every customer-less sale (pending + confirmed), never the assigned.
    assert ids("any") == {pending["id"], confirmed_src["id"]}
    assert assigned["id"] not in ids("any")


def test_list_sales_date_window_half_open(client):
    cat = build_catalog(client)
    store_id, product = cat["store"]["id"], cat["product"]
    s_jan = guest_sale(client, store_id, product["id"])
    s_feb = guest_sale(client, store_id, product["id"])
    s_mar = guest_sale(client, store_id, product["id"])

    # Backdate created_at directly — the checkout API cannot set it.
    session = _session()
    stamps = {
        s_jan["id"]: datetime(2026, 1, 15, 12, 0),
        s_feb["id"]: datetime(2026, 2, 15, 12, 0),
        s_mar["id"]: datetime(2026, 3, 15, 12, 0),
    }
    for sale_id, when in stamps.items():
        session.get(Sale, UUID(sale_id)).created_at = when
    session.commit()

    # Half-open [from, to): Feb 1 <= created_at < Mar 1 -> only February.
    listed = client.get(
        "/api/v1/sales",
        params={
            "store_id": store_id,
            "date_from": "2026-02-01T00:00:00",
            "date_to": "2026-03-01T00:00:00",
        },
    ).json()
    assert [s["id"] for s in listed] == [s_feb["id"]]

    # date_to is exclusive: bound exactly on the March timestamp excludes it.
    upto_mar = client.get(
        "/api/v1/sales",
        params={
            "store_id": store_id,
            "date_to": "2026-03-15T12:00:00",
        },
    ).json()
    assert {s["id"] for s in upto_mar} == {s_jan["id"], s_feb["id"]}


def test_list_sales_limit_and_offset_pagination(client):
    cat = build_catalog(client)
    store_id, product = cat["store"]["id"], cat["product"]
    ids = _order_by_created(client, store_id, product["id"], 5)
    newest_first = list(reversed(ids))

    page1 = client.get(
        "/api/v1/sales", params={"store_id": store_id, "limit": 2, "offset": 0}
    ).json()
    assert [s["id"] for s in page1] == newest_first[0:2]

    page2 = client.get(
        "/api/v1/sales", params={"store_id": store_id, "limit": 2, "offset": 2}
    ).json()
    assert [s["id"] for s in page2] == newest_first[2:4]


def test_list_sales_read_carries_customer_fields(client):
    cat = build_catalog(client)
    store_id, product = cat["store"]["id"], cat["product"]
    customer = make_customer(client, store_id)
    assigned_sale(client, store_id, product["id"], customer["id"])
    guest_sale(client, store_id, product["id"])

    listed = client.get("/api/v1/sales", params={"store_id": store_id}).json()
    by_customer = {s["customer_id"]: s for s in listed}

    named = by_customer[customer["id"]]
    assert named["customer_name"] == "Ali Benali"
    assert named["customer_phone"] == "0550123456"

    walk_in = by_customer[None]
    assert walk_in["customer_name"] is None
    assert walk_in["customer_phone"] is None
