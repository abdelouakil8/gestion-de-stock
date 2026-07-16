"""Factory reset: PIN-gated, wipes every table AND the media directory;
plus the startup create-or-migrate path (prepare_database) that fixes
legacy databases in place."""

from io import BytesIO

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from PIL import Image
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
def client(monkeypatch, tmp_path):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    monkeypatch.setattr(settings, "pin_hash", hash_pin(PIN))
    monkeypatch.setattr(settings, "media_dir", tmp_path / "media")
    app.dependency_overrides[deps.get_db] = lambda: session
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


def seed_everything(client) -> dict:
    store = client.post("/api/v1/stores", json={"name": "Boutique Reset"}).json()
    product = client.post(
        "/api/v1/products",
        json={
            "store_id": store["id"],
            "name": "Eau",
            "cost_price": "25.00",
            "price_detail": "40.00",
            "price_gros": "37.50",
            "price_super_gros": "30.00",
            "stock_quantity": 50,
        },
        headers=PIN_HEADER,
    ).json()
    buffer = BytesIO()
    Image.new("RGB", (8, 8), (1, 2, 3)).save(buffer, format="PNG")
    client.post(
        f"/api/v1/products/{product['id']}/image",
        files={"file": ("p.png", buffer.getvalue(), "image/png")},
        headers=PIN_HEADER,
    )
    customer = client.post(
        "/api/v1/customers",
        json={"store_id": store["id"], "name": "Ali", "phone": "0550"},
    ).json()
    client.post(
        "/api/v1/sales/checkout",
        json={
            "store_id": store["id"],
            "items": [{"product_id": product["id"], "quantity": 2}],
            "payment": {
                "mode": "partial",
                "amount_paid": "10.00",
                "customer_id": customer["id"],
            },
        },
    )
    client.put(
        "/api/v1/settings",
        params={"store_id": store["id"]},
        json={"shop_name": "X"},
        headers=PIN_HEADER,
    )
    return store


@pytest.fixture()
def fk_client(monkeypatch, tmp_path):
    """Like ``client`` but with ``PRAGMA foreign_keys=ON`` — matching the
    production engine (see app/db/session.py). Without this, SQLite silently
    ignores foreign keys and the reset's delete order is never validated, which
    is exactly how the incomplete wipe list shipped a reset that crashes on a
    real install with a FOREIGN KEY constraint error."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @sa.event.listens_for(engine, "connect")
    def _enable_fk(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    session = Session(engine)
    monkeypatch.setattr(settings, "pin_hash", hash_pin(PIN))
    monkeypatch.setattr(settings, "media_dir", tmp_path / "media")
    app.dependency_overrides[deps.get_db] = lambda: session
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


def test_factory_reset_wipes_all_tables_with_foreign_keys_enforced(fk_client, tmp_path):
    """Regression: the wipe must delete EVERY table in FK-safe order.

    A sale writes a stock_movement (and sale_items) that reference products;
    with foreign keys enforced (as in production) the reset fails unless those
    child tables are wiped before products. This guards against the wipe list
    rotting again as new tables are added.
    """
    seed_everything(fk_client)
    result = fk_client.post("/api/v1/admin/factory-reset", headers=PIN_HEADER)
    assert result.status_code == 200, result.text
    deleted = result.json()["deleted"]
    # The tables that were previously missing from the wipe order must now be
    # both present and cleared.
    assert deleted["stock_movements"] >= 1
    assert deleted["stores"] == 1 and deleted["products"] == 1

    assert fk_client.get("/api/v1/stores").json() == []
    # And a fresh store can be created afterwards (no orphaned rows blocking).
    again = fk_client.post("/api/v1/stores", json={"name": "Après reset"})
    assert again.status_code == 201, again.text


def test_factory_reset_requires_pin(client):
    seed_everything(client)
    refused = client.post("/api/v1/admin/factory-reset")
    assert refused.status_code == 401
    assert refused.json()["error"]["code"] == "invalid_pin"
    # Nothing was deleted.
    assert client.get("/api/v1/stores").json() != []


def test_factory_reset_wipes_data_and_media(client, tmp_path):
    store = seed_everything(client)
    media_files = list((tmp_path / "media").rglob("*.png"))
    assert media_files, "seed should have stored an image"

    result = client.post("/api/v1/admin/factory-reset", headers=PIN_HEADER)
    assert result.status_code == 200
    deleted = result.json()["deleted"]
    assert deleted["stores"] == 1
    assert deleted["products"] == 1
    assert deleted["customers"] == 1
    assert deleted["sales"] == 1
    assert deleted["sale_items"] == 1
    assert deleted["payments"] == 1
    assert deleted["store_settings"] == 1

    assert client.get("/api/v1/stores").json() == []
    assert (
        client.get("/api/v1/products", params={"store_id": store["id"]}).json()["items"]
        == []
    )
    assert not any((tmp_path / "media").rglob("*")), "media must be wiped"


# ------------------------------------------- startup create-or-migrate


def test_prepare_database_upgrades_phase5_file_in_place(tmp_path, monkeypatch):
    """The exact scenario from the field: a Phase-5 database opened by the
    new build must be migrated automatically before serving requests."""
    from alembic import command
    from app.db.migrate import alembic_config, prepare_database

    db_path = tmp_path / "legacy.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path.as_posix()}")
    command.upgrade(alembic_config(), "b41c92d7e310")  # a Phase-5 schema

    engine = create_engine(settings.database_url)
    prepare_database(engine)

    columns = {c["name"] for c in sa.inspect(engine).get_columns("products")}
    assert "price_detail" in columns and "min_sale_price" not in columns
    # Idempotent: a second startup is a no-op.
    prepare_database(engine)
    engine.dispose()


def test_prepare_database_stamps_legacy_create_all_database(tmp_path, monkeypatch):
    """Packaged builds used to bootstrap via create_all with NO
    alembic_version — prepare_database must adopt them, not crash."""
    from app.db.migrate import prepare_database
    from app.models import Base as CurrentBase

    db_path = tmp_path / "createall.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path.as_posix()}")
    engine = create_engine(settings.database_url)
    CurrentBase.metadata.create_all(engine)  # current-generation schema

    prepare_database(engine)  # must stamp head then no-op, not re-create

    inspector = sa.inspect(engine)
    assert "alembic_version" in inspector.get_table_names()
    prepare_database(engine)  # still fine on the next startup
    engine.dispose()


def test_prepare_database_bootstraps_fresh_file(tmp_path, monkeypatch):
    from app.db.migrate import prepare_database

    db_path = tmp_path / "fresh.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path.as_posix()}")
    engine = create_engine(settings.database_url)
    prepare_database(engine)
    inspector = sa.inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"stores", "products", "customers", "payments", "alembic_version"} <= tables
    engine.dispose()
