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
