"""Customer Attach + Guest Sale + Smart Search — search & normalization.

Two layers, per the project's per-file fixture convention (the shared ``db``
fixture lives in conftest.py; the ``client`` fixture is defined locally, copied
from test_api.py):

* Unit level — ``app.core.textnorm.normalize_text`` canonicalisation (French
  accents, Arabic tashkeel/folding/tatweel, casefold, whitespace, digits).
* HTTP level — GET /api/v1/customers and GET /api/v1/products smart search
  (accent/Arabic-insensitive matching, phone tokens, LIKE-wildcard escaping,
  ranking exact-first, recency tie-break for customers, limit, fuzzy typo
  fallback for products, active_only, and the untouched no-arg / by-barcode
  paths).

GET /customers and GET /products need NO PIN; POST /products is PIN-gated.
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
from app.core.textnorm import normalize_text
from app.main import app
from app.models import Base

PIN = "1234"
PIN_HEADER = {"X-Owner-Pin": PIN}


@pytest.fixture()
def client(monkeypatch):
    """TestClient wired to a fresh in-memory DB and a known PIN (test_api.py)."""
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


# --------------------------------------------------------------- helpers


def make_store(client, name="Boutique Recherche") -> str:
    """Create a store via the API, return its id."""
    resp = client.post("/api/v1/stores", json={"name": name})
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


def make_customer(client, store_id, name, phone, note=None) -> dict:
    """Create a customer via the API (no PIN needed)."""
    body = {"store_id": store_id, "name": name, "phone": phone}
    if note is not None:
        body["note"] = note
    resp = client.post("/api/v1/customers", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


def make_product(
    client,
    store_id,
    name,
    *,
    barcode=None,
    detail="40.00",
    is_active=True,
    stock=100,
) -> dict:
    """Create a product via the PIN-gated owner endpoint."""
    body = {
        "store_id": store_id,
        "name": name,
        "barcode": barcode,
        "cost_price": "25.00",
        "price_detail": detail,
        "price_gros": detail,
        "price_super_gros": "0.10",
        "stock_quantity": stock,
        "is_active": is_active,
    }
    resp = client.post("/api/v1/products", json=body, headers=PIN_HEADER)
    assert resp.status_code == 201, resp.text
    return resp.json()


def search_customers(client, store_id, q=None, limit=None) -> list[dict]:
    params = {"store_id": store_id}
    if q is not None:
        params["q"] = q
    if limit is not None:
        params["limit"] = limit
    resp = client.get("/api/v1/customers", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def search_products(client, store_id, q=None, limit=None, active_only=None):
    params = {"store_id": store_id}
    if q is not None:
        params["q"] = q
    if limit is not None:
        params["limit"] = limit
    if active_only is not None:
        params["active_only"] = active_only
    resp = client.get("/api/v1/products", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def checkout_full(client, store_id, product_id, customer_id) -> dict:
    """Finalize a full-payment sale attached to a customer (drives recency)."""
    resp = client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": store_id,
            "items": [{"product_id": product_id, "quantity": 1}],
            "payment": {"mode": "full", "customer_id": customer_id},
        },
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


# ============================================================ unit: textnorm


def test_normalize_none_and_empty_are_empty_string():
    assert normalize_text(None) == ""
    assert normalize_text("") == ""


def test_normalize_strips_french_accents():
    assert normalize_text("Café") == normalize_text("cafe")
    assert normalize_text("Café") == "cafe"


def test_normalize_strips_arabic_tashkeel():
    assert normalize_text("مُحَمَّد") == normalize_text("محمد")


def test_normalize_folds_arabic_letters_and_tatweel():
    # Alif forms fold to bare alif.
    assert normalize_text("أحمد") == normalize_text("احمد")
    # Ta marbuta -> ha.
    assert normalize_text("مدرسة") == normalize_text("مدرسه")
    # Alif maksura -> ya.
    assert normalize_text("ى") == normalize_text("ي")
    # Tatweel (ornamental stretch) is removed.
    assert normalize_text("مـحـمـد") == "محمد"


def test_normalize_casefold_whitespace_and_digits():
    assert normalize_text("MacDonald") == "macdonald"
    assert normalize_text("  a   b ") == "a b"
    # Digits and punctuation survive (phones, barcodes).
    assert normalize_text("0550-12") == "0550-12"


# ==================================================== HTTP: customer search


def test_customer_search_accent_insensitive(client):
    store = make_store(client)
    make_customer(client, store, "Cafétéria", "0550000001")
    names = [c["name"] for c in search_customers(client, store, q="cafeteria")]
    assert names == ["Cafétéria"]


def test_customer_search_arabic_folding(client):
    store = make_store(client)
    make_customer(client, store, "أحمد", "0550000010")
    make_customer(client, store, "احمد", "0550000011")
    make_customer(client, store, "Brahim", "0550000012")
    names = {c["name"] for c in search_customers(client, store, q="احمد")}
    assert names == {"أحمد", "احمد"}


def test_customer_search_by_phone_token(client):
    store = make_store(client)
    make_customer(client, store, "Client Un", "0555111111")
    make_customer(client, store, "Client Deux", "0660222222")
    names = [c["name"] for c in search_customers(client, store, q="555")]
    assert names == ["Client Un"]


def test_customer_search_escapes_like_wildcards(client):
    store = make_store(client)
    special = make_customer(client, store, "50%_off", "0550000020")
    make_customer(client, store, "Autre", "0550000021")

    # The literal "%" must be escaped, not treated as a LIKE wildcard: q="50%"
    # finds the special customer.
    hit = [c["name"] for c in search_customers(client, store, q="50%")]
    assert hit == ["50%_off"]

    # And q="a" must NOT match everyone via a stray "%": it should only match
    # rows whose search_text actually contains "a" (here just "Autre").
    a_names = {c["name"] for c in search_customers(client, store, q="a")}
    assert a_names == {"Autre"}
    assert special["name"] not in a_names


def test_customer_search_ranks_exact_first(client):
    store = make_store(client)
    make_customer(client, store, "Ali", "0550000030")
    make_customer(client, store, "Alice", "0550000031")
    make_customer(client, store, "Talib Ali", "0550000032")
    results = search_customers(client, store, q="ali")
    # Exact normalized match ("Ali") outranks prefix ("Alice") and token match.
    assert results[0]["name"] == "Ali"


def test_customer_search_recency_tie_break(client):
    store = make_store(client)
    product = make_product(client, store, "Article recence")
    sara_a = make_customer(client, store, "Sara A", "0550000040")
    sara_b = make_customer(client, store, "Sara B", "0550000041")
    # Only Sara B has a (recent) sale -> she wins the recency tie-break.
    checkout_full(client, store, product["id"], sara_b["id"])
    results = search_customers(client, store, q="sara")
    names = [c["name"] for c in results]
    assert set(names) == {"Sara A", "Sara B"}
    assert results[0]["name"] == "Sara B"
    assert results[0]["id"] == sara_b["id"]
    assert sara_a["id"] in {c["id"] for c in results}


def test_customer_search_respects_limit(client):
    store = make_store(client)
    for i in range(4):
        make_customer(client, store, f"Commun {i}", f"05500001{i}0")
    results = search_customers(client, store, q="commun", limit=2)
    assert len(results) <= 2


def test_customer_search_empty_query_returns_all_unlimited(client):
    store = make_store(client)
    for i in range(3):
        make_customer(client, store, f"Client {i}", f"05500002{i}0")
    # No q -> old behavior: every customer, ordered by name, no cap.
    results = search_customers(client, store)
    assert [c["name"] for c in results] == ["Client 0", "Client 1", "Client 2"]


# ===================================================== HTTP: product search


def test_product_search_fuzzy_typo_fallback(client):
    store = make_store(client)
    make_product(client, store, "Yaourt")
    # Exact spelling works.
    assert [p["name"] for p in search_products(client, store, q="yaourt")] == [
        "Yaourt"
    ]
    # Transposition "yauort" is caught by the fuzzy fallback.
    fuzzy = [p["name"] for p in search_products(client, store, q="yauort")]
    assert "Yaourt" in fuzzy


def test_product_search_active_only_filter(client):
    store = make_store(client)
    make_product(client, store, "Lait actif", is_active=True)
    make_product(client, store, "Lait inactif", is_active=False)

    default = {p["name"] for p in search_products(client, store, q="lait")}
    assert default == {"Lait actif", "Lait inactif"}

    active = {
        p["name"] for p in search_products(client, store, q="lait", active_only=True)
    }
    assert active == {"Lait actif"}


def test_product_no_arg_list_returns_full_catalog(client):
    store = make_store(client)
    make_product(client, store, "Aaa produit")
    make_product(client, store, "Bbb produit", is_active=False)
    make_product(client, store, "Ccc produit")
    # No filters -> full catalog (incl. inactive), ordered by name.
    results = search_products(client, store)
    assert [p["name"] for p in results] == [
        "Aaa produit",
        "Bbb produit",
        "Ccc produit",
    ]


def test_product_by_barcode_still_returns_exact_product(client):
    store = make_store(client)
    make_product(client, store, "Produit code", barcode="6130000000015")
    resp = client.get(
        "/api/v1/products/by-barcode/6130000000015",
        params={"store_id": store},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["name"] == "Produit code"
    # ProductRead is cashier-safe: never leaks cost_price.
    assert "cost_price" not in resp.json()
    _ = Decimal  # imported for parity with money-typed helpers
