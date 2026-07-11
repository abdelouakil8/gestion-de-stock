"""Phase 6 definition-of-done for Alembic: `upgrade head` works from
scratch, AND a Phase-5 database upgrades in place with the documented
backfills (named prices from tiers + floor, paid_amount, Payment history,
price_level, price_tiers dropped)."""

import uuid
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.config import Config

from alembic import command
from app.core.config import settings

BACKEND_DIR = Path(__file__).resolve().parents[1]
PHASE5_REV = "b41c92d7e310"
PHASE6_REV = "c9a1e4b7d2f0"
PHASE7_REV = "d4f8a1c07e2b"
PHASE8_REV = "e5b2c9f4a3d1"
PHASE11_REV = "b2c3d4e5f6a7"
PHASE12_REV = "c3d4e5f6a7b8"
PHASE13_REV = "d5e6f7a8b9c0"
PHASE14_REV = "e7f8a9b0c1d2"  # current head


@pytest.fixture()
def alembic_cfg(tmp_path, monkeypatch):
    """Alembic config pointed at a throwaway SQLite file."""
    db_path = tmp_path / "migrate.db"
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path.as_posix()}")
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg, db_path


def test_upgrade_head_from_scratch(alembic_cfg):
    cfg, db_path = alembic_cfg
    command.upgrade(cfg, "head")

    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    inspector = sa.inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"customers", "payments", "store_settings"} <= tables
    assert "price_tiers" not in tables

    product_cols = {c["name"] for c in inspector.get_columns("products")}
    assert {
        "price_detail",
        "price_gros",
        "price_super_gros",
        "image_path",
        "low_stock_threshold",
    } <= product_cols
    assert "min_sale_price" not in product_cols

    sale_cols = {c["name"] for c in inspector.get_columns("sales")}
    assert {"customer_id", "paid_amount"} <= sale_cols
    assert "price_level" in {c["name"] for c in inspector.get_columns("sale_items")}
    engine.dispose()


def test_phase5_database_upgrades_in_place_with_backfills(alembic_cfg):
    cfg, db_path = alembic_cfg
    command.upgrade(cfg, PHASE5_REV)

    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    store_id = uuid.uuid4().hex
    p_tiered, p_bare = uuid.uuid4().hex, uuid.uuid4().hex
    sale_id, item_id = uuid.uuid4().hex, uuid.uuid4().hex
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO stores (id, name, created_at, updated_at)"
            " VALUES (?, 'Legacy', '2026-01-01', '2026-01-01')",
            (store_id,),
        )
        # Product with tiers 1→40.00, 6→37.50 (cents) and floor 30.00.
        conn.exec_driver_sql(
            "INSERT INTO products (id, store_id, name, cost_price,"
            " min_sale_price, stock_quantity, is_active, created_at, updated_at)"
            " VALUES (?, ?, 'Eau', 2500, 3000, 100, 1, '2026-01-01', '2026-01-01')",
            (p_tiered, store_id),
        )
        for qty, cents in [(1, 4000), (6, 3750)]:
            conn.exec_driver_sql(
                "INSERT INTO price_tiers (id, store_id, product_id, min_quantity,"
                " unit_price, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, '2026-01-01', '2026-01-01')",
                (uuid.uuid4().hex, store_id, p_tiered, qty, cents),
            )
        # Product with no tiers, floor 50.00.
        conn.exec_driver_sql(
            "INSERT INTO products (id, store_id, name, cost_price,"
            " min_sale_price, stock_quantity, is_active, created_at, updated_at)"
            " VALUES (?, ?, 'Riz', 4500, 5000, 40, 1, '2026-01-01', '2026-01-01')",
            (p_bare, store_id),
        )
        # Regression: an id whose TEXT differs from sa.Uuid's lowercase
        # rendering (e.g. uppercase hex) must still be backfilled — the
        # migration treats keys as opaque strings.
        conn.exec_driver_sql(
            "INSERT INTO products (id, store_id, name, cost_price,"
            " min_sale_price, stock_quantity, is_active, created_at, updated_at)"
            " VALUES (?, ?, 'Majuscules', 100, 200, 5, 1,"
            " '2026-01-01', '2026-01-01')",
            (uuid.uuid4().hex.upper(), store_id),
        )
        # One historical sale (6 × 37.50 = 225.00).
        conn.exec_driver_sql(
            "INSERT INTO sales (id, store_id, total_amount, created_at, updated_at)"
            " VALUES (?, ?, 22500, '2026-02-01 10:00:00', '2026-02-01 10:00:00')",
            (sale_id, store_id),
        )
        conn.exec_driver_sql(
            "INSERT INTO sale_items (id, store_id, sale_id, product_id, quantity,"
            " unit_price_applied, line_total, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, 6, 3750, 22500,"
            " '2026-02-01 10:00:00', '2026-02-01 10:00:00')",
            (item_id, store_id, sale_id, p_tiered),
        )
    engine.dispose()

    command.upgrade(cfg, "head")

    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.connect() as conn:
        # Documented backfill: detail = tier-1, gros = tier-2 (clamped),
        # super_gros = min_sale_price.
        assert conn.exec_driver_sql(
            "SELECT price_detail, price_gros, price_super_gros FROM products"
            " WHERE id = ?",
            (p_tiered,),
        ).one() == (4000, 3750, 3000)
        # No tiers: everything collapses to the floor.
        assert conn.exec_driver_sql(
            "SELECT price_detail, price_gros, price_super_gros FROM products"
            " WHERE id = ?",
            (p_bare,),
        ).one() == (5000, 5000, 5000)
        # The uppercase-hex id was backfilled too (no NULLs anywhere).
        assert conn.exec_driver_sql(
            "SELECT price_detail, price_gros, price_super_gros FROM products"
            " WHERE name = 'Majuscules'"
        ).one() == (200, 200, 200)
        assert (
            conn.exec_driver_sql(
                "SELECT count(*) FROM products WHERE price_detail IS NULL"
            ).scalar()
            == 0
        )
        # Historical sales are fully paid, with an auditable Payment row.
        assert conn.exec_driver_sql(
            "SELECT paid_amount, customer_id FROM sales WHERE id = ?", (sale_id,)
        ).one() == (22500, None)
        payments = conn.exec_driver_sql("SELECT amount, sale_id FROM payments").all()
        assert len(payments) == 1 and payments[0][0] == 22500
        # Legacy lines are labeled with the default level.
        assert (
            conn.exec_driver_sql(
                "SELECT price_level FROM sale_items WHERE id = ?", (item_id,)
            ).scalar()
            == "detail"
        )
        # price_tiers is gone (decision documented in the migration).
        assert (
            conn.exec_driver_sql(
                "SELECT count(*) FROM sqlite_master"
                " WHERE type='table' AND name='price_tiers'"
            ).scalar()
            == 0
        )
    engine.dispose()


def test_downgrade_roundtrip_restores_phase5_schema(alembic_cfg):
    cfg, db_path = alembic_cfg
    command.upgrade(cfg, "head")
    command.downgrade(cfg, PHASE5_REV)

    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    inspector = sa.inspect(engine)
    product_cols = {c["name"] for c in inspector.get_columns("products")}
    assert "min_sale_price" in product_cols
    assert "price_detail" not in product_cols
    assert "price_tiers" in inspector.get_table_names()
    assert "customers" not in inspector.get_table_names()
    engine.dispose()


def test_phase7_backfills_search_text_with_accents_and_arabic(alembic_cfg):
    """Phase-7 upgrade populates products.search_text / customers.search_text
    with the SAME normalize_text the services use at write-time, so accented
    French and Arabic rows become searchable (no NULLs left behind)."""
    from app.core.textnorm import normalize_text

    cfg, db_path = alembic_cfg
    command.upgrade(cfg, PHASE6_REV)

    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    store_id = uuid.uuid4().hex
    # (id, name, barcode) — barcode intentionally None for the Arabic row.
    products = [
        (uuid.uuid4().hex, "Café Noir", "1234567"),
        (uuid.uuid4().hex, "قهوة", None),
        (uuid.uuid4().hex, "Yaourt أبيض", "9990001"),
    ]
    # (id, name, phone, note) — one with a note, one without.
    customers = [
        (uuid.uuid4().hex, "Amélie Café", "0612345678", "Fidèle"),
        (uuid.uuid4().hex, "قهوة أحمد", "0698765432", None),
    ]
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO stores (id, name, created_at, updated_at)"
            " VALUES (?, 'Boutique', '2026-01-01', '2026-01-01')",
            (store_id,),
        )
        for product_id, name, barcode in products:
            # search_text column does not exist yet at phase 6 — do not insert it.
            # Named prices are NOT NULL with a CHECK detail>=gros>=super_gros.
            conn.exec_driver_sql(
                "INSERT INTO products (id, store_id, name, barcode, cost_price,"
                " price_detail, price_gros, price_super_gros, stock_quantity,"
                " is_active, low_stock_threshold, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, 1000, 2000, 2000, 2000, 10, 1, 5,"
                " '2026-01-01', '2026-01-01')",
                (product_id, store_id, name, barcode),
            )
        for customer_id, name, phone, note in customers:
            conn.exec_driver_sql(
                "INSERT INTO customers (id, store_id, name, phone, note,"
                " created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, '2026-01-01', '2026-01-01')",
                (customer_id, store_id, name, phone, note),
            )
    engine.dispose()

    command.upgrade(cfg, PHASE7_REV)

    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.connect() as conn:
        for product_id, name, barcode in products:
            stored = conn.exec_driver_sql(
                "SELECT search_text FROM products WHERE id = ?", (product_id,)
            ).scalar()
            assert stored is not None
            assert stored == normalize_text(f"{name} {barcode or ''}")
        for customer_id, name, phone, note in customers:
            stored = conn.exec_driver_sql(
                "SELECT search_text FROM customers WHERE id = ?", (customer_id,)
            ).scalar()
            assert stored is not None
            assert stored == normalize_text(f"{name} {phone} {note or ''}")
        # Nothing left NULL anywhere.
        assert (
            conn.exec_driver_sql(
                "SELECT count(*) FROM products WHERE search_text IS NULL"
            ).scalar()
            == 0
        )
        assert (
            conn.exec_driver_sql(
                "SELECT count(*) FROM customers WHERE search_text IS NULL"
            ).scalar()
            == 0
        )
    engine.dispose()


def test_phase7_marks_existing_guest_sales_as_confirmed(alembic_cfg):
    """Existing walk-in sales (customer_id IS NULL) are backfilled to their own
    created_at (accepted as intentionally anonymous); sales that already carry
    a customer keep guest_confirmed_at NULL."""
    cfg, db_path = alembic_cfg
    command.upgrade(cfg, PHASE6_REV)

    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    store_id = uuid.uuid4().hex
    customer_id = uuid.uuid4().hex
    sale_assigned = uuid.uuid4().hex
    sale_guest = uuid.uuid4().hex
    guest_created_at = "2026-02-01 10:30:00"
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO stores (id, name, created_at, updated_at)"
            " VALUES (?, 'Boutique', '2026-01-01', '2026-01-01')",
            (store_id,),
        )
        conn.exec_driver_sql(
            "INSERT INTO customers (id, store_id, name, phone, created_at,"
            " updated_at) VALUES (?, ?, 'Client', '0600000000',"
            " '2026-01-01', '2026-01-01')",
            (customer_id, store_id),
        )
        # Sale with a customer -> guest_confirmed_at must stay NULL.
        conn.exec_driver_sql(
            "INSERT INTO sales (id, store_id, customer_id, total_amount,"
            " paid_amount, created_at, updated_at)"
            " VALUES (?, ?, ?, 5000, 5000, '2026-02-01 09:00:00',"
            " '2026-02-01 09:00:00')",
            (sale_assigned, store_id, customer_id),
        )
        # Walk-in sale (customer_id NULL) -> gets created_at as guest_confirmed_at.
        conn.exec_driver_sql(
            "INSERT INTO sales (id, store_id, total_amount, paid_amount,"
            " created_at, updated_at) VALUES (?, ?, 3000, 3000, ?, ?)",
            (sale_guest, store_id, guest_created_at, guest_created_at),
        )
    engine.dispose()

    command.upgrade(cfg, PHASE7_REV)

    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    with engine.connect() as conn:
        guest_confirmed, created_at = conn.exec_driver_sql(
            "SELECT guest_confirmed_at, created_at FROM sales WHERE id = ?",
            (sale_guest,),
        ).one()
        assert guest_confirmed is not None
        assert guest_confirmed == created_at
        assert (
            conn.exec_driver_sql(
                "SELECT guest_confirmed_at FROM sales WHERE id = ?",
                (sale_assigned,),
            ).scalar()
            is None
        )
    engine.dispose()


def test_prepare_database_recognizes_head_marker(alembic_cfg):
    """A legacy create_all database already at head (product_packagings table
    present, no alembic_version) is stamped straight to head — no double-apply
    error. The marker is the product_packagings table (phase 8)."""
    from app import models
    from app.db.migrate import prepare_database

    cfg, db_path = alembic_cfg
    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    models.Base.metadata.create_all(engine)
    # Simulate a legacy create_all bootstrap: no alembic_version row.
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")

    prepare_database(engine)

    with engine.connect() as conn:
        version = conn.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar()
    assert version == PHASE14_REV
    engine.dispose()


def test_prepare_database_upgrades_phase6_legacy_create_all_to_head(alembic_cfg):
    """A legacy create_all database at phase 6 (no search_text, no
    product_packagings, no alembic_version) is stamped at phase 6 then upgraded
    to head, adding the products.search_text column (phase 7) and the
    product_packagings table (phase 8)."""
    from app.db.migrate import prepare_database

    cfg, db_path = alembic_cfg
    command.upgrade(cfg, PHASE6_REV)

    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    # Legacy create_all look-alike: drop the alembic bookkeeping table.
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    # Sanity: phase-6 schema has no search_text yet.
    assert "search_text" not in {
        c["name"] for c in sa.inspect(engine).get_columns("products")
    }

    prepare_database(engine)

    inspector = sa.inspect(engine)
    with engine.connect() as conn:
        version = conn.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar()
    assert version == PHASE14_REV
    assert "search_text" in {c["name"] for c in inspector.get_columns("products")}
    assert "product_packagings" in inspector.get_table_names()
    engine.dispose()


def test_phase8_creates_product_packagings_and_sale_item_columns(alembic_cfg):
    """Phase-8 upgrade adds the product_packagings table (with its two CHECK
    backstops) and the three sale_items snapshot columns. A pre-existing
    sale_item row is backfilled to unit_count == 1 via the server_default, so
    base_units = quantity * unit_count stays == quantity for legacy lines."""
    cfg, db_path = alembic_cfg
    command.upgrade(cfg, PHASE7_REV)

    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    store_id = uuid.uuid4().hex
    product_id = uuid.uuid4().hex
    sale_id, item_id = uuid.uuid4().hex, uuid.uuid4().hex
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO stores (id, name, created_at, updated_at)"
            " VALUES (?, 'Boutique', '2026-01-01', '2026-01-01')",
            (store_id,),
        )
        conn.exec_driver_sql(
            "INSERT INTO products (id, store_id, name, cost_price, price_detail,"
            " price_gros, price_super_gros, stock_quantity, is_active,"
            " low_stock_threshold, search_text, created_at, updated_at)"
            " VALUES (?, ?, 'Eau', 1000, 2000, 2000, 2000, 100, 1, 5, 'eau',"
            " '2026-01-01', '2026-01-01')",
            (product_id, store_id),
        )
        conn.exec_driver_sql(
            "INSERT INTO sales (id, store_id, total_amount, paid_amount,"
            " created_at, updated_at)"
            " VALUES (?, ?, 8000, 8000, '2026-02-01 10:00:00',"
            " '2026-02-01 10:00:00')",
            (sale_id, store_id),
        )
        # A legacy line (4 × 20.00 = 80.00), pre-packaging: no packaging
        # columns are inserted, so they must fall to their defaults.
        conn.exec_driver_sql(
            "INSERT INTO sale_items (id, store_id, sale_id, product_id, quantity,"
            " unit_price_applied, line_total, created_at, updated_at)"
            " VALUES (?, ?, ?, ?, 4, 2000, 8000,"
            " '2026-02-01 10:00:00', '2026-02-01 10:00:00')",
            (item_id, store_id, sale_id, product_id),
        )
    engine.dispose()

    command.upgrade(cfg, "head")

    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    inspector = sa.inspect(engine)

    # product_packagings exists with the documented column set.
    assert "product_packagings" in inspector.get_table_names()
    packaging_cols = {c["name"] for c in inspector.get_columns("product_packagings")}
    assert {
        "id",
        "product_id",
        "label",
        "unit_count",
        "price_detail",
        "price_gros",
        "price_super_gros",
        "position",
        "is_active",
        "store_id",
        "created_at",
        "updated_at",
        "deleted_at",
    } <= packaging_cols

    # Both CHECK backstops are present under their short names.
    check_names = {
        ck["name"] for ck in inspector.get_check_constraints("product_packagings")
    }
    assert {
        "ck_product_packagings_packaging_unit_count_positive",
        "ck_product_packagings_packaging_price_levels_ordered",
    } <= check_names

    # sale_items gained the three snapshot columns.
    sale_item_cols = {c["name"] for c in inspector.get_columns("sale_items")}
    assert {"packaging_id", "packaging_label", "unit_count"} <= sale_item_cols

    with engine.connect() as conn:
        # Existing line: unit_count backfilled to 1 (server_default), and the
        # nullable snapshot columns stay NULL.
        packaging_id, packaging_label, unit_count = conn.exec_driver_sql(
            "SELECT packaging_id, packaging_label, unit_count FROM sale_items"
            " WHERE id = ?",
            (item_id,),
        ).one()
        assert unit_count == 1
        assert packaging_id is None
        assert packaging_label is None
        # No unit_count NULLs anywhere (NOT NULL column).
        assert (
            conn.exec_driver_sql(
                "SELECT count(*) FROM sale_items WHERE unit_count IS NULL"
            ).scalar()
            == 0
        )
    engine.dispose()


def test_prepare_database_recognizes_phase8_marker(alembic_cfg):
    """A fresh create_all database is stamped straight to head and carries the
    phase-8 product_packagings table."""
    from app import models
    from app.db.migrate import prepare_database

    cfg, db_path = alembic_cfg
    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    models.Base.metadata.create_all(engine)

    prepare_database(engine)

    inspector = sa.inspect(engine)
    with engine.connect() as conn:
        version = conn.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar()
    assert version == PHASE14_REV
    assert "product_packagings" in inspector.get_table_names()
    engine.dispose()


def test_prepare_database_upgrades_phase7_legacy_to_phase8(alembic_cfg):
    """A legacy create_all database at phase 7 (search_text present, but no
    product_packagings and no alembic_version) is stamped at phase 7 then
    upgraded to head, adding the product_packagings table (phase 8)."""
    from app.db.migrate import prepare_database

    cfg, db_path = alembic_cfg
    command.upgrade(cfg, PHASE7_REV)

    engine = sa.create_engine(f"sqlite:///{db_path.as_posix()}")
    # Legacy create_all look-alike: drop the alembic bookkeeping table.
    with engine.begin() as conn:
        conn.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    inspector = sa.inspect(engine)
    # Sanity: phase-7 schema has search_text but not the phase-8 table.
    assert "search_text" in {c["name"] for c in inspector.get_columns("products")}
    assert "product_packagings" not in inspector.get_table_names()

    prepare_database(engine)

    inspector = sa.inspect(engine)
    with engine.connect() as conn:
        version = conn.exec_driver_sql(
            "SELECT version_num FROM alembic_version"
        ).scalar()
    assert version == PHASE14_REV
    assert "product_packagings" in inspector.get_table_names()
    engine.dispose()
