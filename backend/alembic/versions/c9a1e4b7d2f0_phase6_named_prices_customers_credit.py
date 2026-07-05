"""Phase 6: named price levels, customers & credit, images, settings.

Revision ID: c9a1e4b7d2f0
Revises: b41c92d7e310
Create Date: 2026-07-03 10:00:00.000000

What this migration does (all backfills run in Python on the connection,
so the same code works on SQLite today and PostgreSQL later; monetary
columns are BIGINT integer cents throughout — exact arithmetic only):

1. products — new columns price_detail / price_gros / price_super_gros
   (named sale prices), image_path, low_stock_threshold (default 5).
   Backfill, per product (cents):
     price_super_gros = min_sale_price               (the historic floor)
     price_detail     = unit_price of the LOWEST-min_quantity non-deleted
                        tier if the product had tiers, else min_sale_price;
                        never below min_sale_price (bad legacy data is
                        raised to the floor, keeping the ordering valid)
     price_gros       = unit_price of the SECOND-lowest tier clamped into
                        [price_super_gros, price_detail] if such a tier
                        exists, else price_super_gros
   min_sale_price is then DROPPED: the floor now IS price_super_gros.
   A CHECK constraint enforces price_detail >= price_gros >=
   price_super_gros at the database level.

2. price_tiers is DROPPED (decision: remove, not archive). Rationale:
   tiers were pricing *configuration*, not financial records — every price
   actually charged lives on sale_items.unit_price_applied. Keeping a
   dead table would leave create_all() (fresh installs) and migrated
   databases with diverging schemas. The relevant data is preserved by
   the backfill above.

3. customers — new table; phone unique per store among non-deleted rows
   (partial unique index, SQLite and PostgreSQL syntax both emitted).

4. sales — new customer_id (nullable FK) and paid_amount. Backfill:
   paid_amount = total_amount (every pre-phase-6 sale was paid in full at
   checkout — credit sales did not exist yet).

5. payments — new table. Backfill: one Payment row per existing sale with
   total_amount > 0, amount = total_amount, created_at = the sale's
   created_at, so the invariant paid_amount == SUM(payments) holds for
   historical data too and the payment history stays auditable.

6. sale_items — new price_level column, backfilled to 'detail' (the only
   sensible label for pre-phase-6 lines).

7. store_settings — new table (rows are created lazily by the service).
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9a1e4b7d2f0"
down_revision: str | Sequence[str] | None = "b41c92d7e310"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _base_columns() -> list[sa.Column]:
    """The project-wide mandatory columns (same shape as existing tables)."""
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_synced", sa.Boolean(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------------------ 3. customers
    op.create_table(
        "customers",
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=False),
        sa.Column("note", sa.String(length=500), nullable=True),
        *_base_columns(),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["store_id"], ["stores.id"], name=op.f("fk_customers_store_id_stores")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_customers")),
    )
    with op.batch_alter_table("customers", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_customers_store_id"), ["store_id"], unique=False
        )
    op.create_index(
        "uq_customers_store_phone_active",
        "customers",
        ["store_id", "phone"],
        unique=True,
        sqlite_where=sa.text("deleted_at IS NULL"),
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # -------------------------------------------------- 7. store_settings
    op.create_table(
        "store_settings",
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("shop_name", sa.String(length=120), nullable=True),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("address", sa.String(length=200), nullable=True),
        sa.Column("footer_message", sa.String(length=200), nullable=True),
        sa.Column("show_credit_details", sa.Boolean(), nullable=False),
        sa.Column("ui_language", sa.String(length=2), nullable=False),
        sa.Column("theme_accent", sa.String(length=7), nullable=False),
        *_base_columns(),
        sa.ForeignKeyConstraint(
            ["store_id"], ["stores.id"], name=op.f("fk_store_settings_store_id_stores")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_store_settings")),
    )
    # Single UNIQUE index — same object the ORM (unique=True, index=True)
    # emits, so create_all() and alembic head produce identical schemas.
    with op.batch_alter_table("store_settings", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_store_settings_store_id"), ["store_id"], unique=True
        )

    # -------------------------------------------------------- 5. payments
    op.create_table(
        "payments",
        sa.Column("sale_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        *_base_columns(),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint("amount > 0", name=op.f("ck_payments_amount_positive")),
        sa.ForeignKeyConstraint(
            ["sale_id"], ["sales.id"], name=op.f("fk_payments_sale_id_sales")
        ),
        sa.ForeignKeyConstraint(
            ["store_id"], ["stores.id"], name=op.f("fk_payments_store_id_stores")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payments")),
    )
    with op.batch_alter_table("payments", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_payments_sale_id"), ["sale_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_payments_store_id"), ["store_id"], unique=False
        )

    # ------------------------------------- 1. products: new price columns
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.add_column(sa.Column("price_detail", sa.BigInteger(), nullable=True))
        batch_op.add_column(sa.Column("price_gros", sa.BigInteger(), nullable=True))
        batch_op.add_column(
            sa.Column("price_super_gros", sa.BigInteger(), nullable=True)
        )
        batch_op.add_column(
            sa.Column("image_path", sa.String(length=255), nullable=True)
        )
        batch_op.add_column(
            sa.Column(
                "low_stock_threshold",
                sa.Integer(),
                nullable=False,
                server_default="5",
            )
        )

    # Backfill named prices from min_sale_price + legacy tiers (in cents).
    # NB: id columns are declared as raw String here ON PURPOSE — the Uuid
    # type would rewrite values (lowercase hex) on the round-trip, and a
    # WHERE on a rewritten key silently matches nothing. Backfills must
    # treat keys as opaque.
    products_t = sa.table(
        "products",
        sa.column("id", sa.String()),
        sa.column("min_sale_price", sa.BigInteger()),
        sa.column("price_detail", sa.BigInteger()),
        sa.column("price_gros", sa.BigInteger()),
        sa.column("price_super_gros", sa.BigInteger()),
    )
    tiers_t = sa.table(
        "price_tiers",
        sa.column("product_id", sa.String()),
        sa.column("min_quantity", sa.Integer()),
        sa.column("unit_price", sa.BigInteger()),
        sa.column("deleted_at", sa.DateTime(timezone=True)),
    )

    tier_rows = bind.execute(
        sa.select(tiers_t.c.product_id, tiers_t.c.min_quantity, tiers_t.c.unit_price)
        .where(tiers_t.c.deleted_at.is_(None))
        .order_by(tiers_t.c.product_id, tiers_t.c.min_quantity)
    ).all()
    tiers_by_product: dict[object, list[int]] = {}
    for product_id, _min_qty, unit_price in tier_rows:
        tiers_by_product.setdefault(product_id, []).append(unit_price)

    for product_id, floor in bind.execute(
        sa.select(products_t.c.id, products_t.c.min_sale_price)
    ).all():
        tier_prices = tiers_by_product.get(product_id, [])
        detail = max(tier_prices[0], floor) if tier_prices else floor
        if len(tier_prices) >= 2:
            gros = min(max(tier_prices[1], floor), detail)
        else:
            gros = floor
        bind.execute(
            sa.update(products_t)
            .where(products_t.c.id == product_id)
            .values(price_detail=detail, price_gros=gros, price_super_gros=floor)
        )

    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.alter_column(
            "price_detail", existing_type=sa.BigInteger(), nullable=False
        )
        batch_op.alter_column(
            "price_gros", existing_type=sa.BigInteger(), nullable=False
        )
        batch_op.alter_column(
            "price_super_gros", existing_type=sa.BigInteger(), nullable=False
        )
        batch_op.drop_column("min_sale_price")
        batch_op.create_check_constraint(
            "price_levels_ordered",
            "price_detail >= price_gros AND price_gros >= price_super_gros",
        )

    # ------------------------------------------- 2. drop legacy price_tiers
    with op.batch_alter_table("price_tiers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_price_tiers_store_id"))
        batch_op.drop_index(batch_op.f("ix_price_tiers_product_id"))
    op.drop_table("price_tiers")

    # -------------------------------- 4. sales: customer_id + paid_amount
    with op.batch_alter_table("sales", schema=None) as batch_op:
        batch_op.add_column(sa.Column("customer_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "paid_amount", sa.BigInteger(), nullable=False, server_default="0"
            )
        )
        batch_op.create_index(
            batch_op.f("ix_sales_customer_id"), ["customer_id"], unique=False
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_sales_customer_id_customers"),
            "customers",
            ["customer_id"],
            ["id"],
        )

    # Raw String ids again: copied values must pass through untouched.
    sales_t = sa.table(
        "sales",
        sa.column("id", sa.String()),
        sa.column("total_amount", sa.BigInteger()),
        sa.column("paid_amount", sa.BigInteger()),
        sa.column("store_id", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    # Every pre-phase-6 sale was paid in full at checkout.
    bind.execute(sa.update(sales_t).values(paid_amount=sales_t.c.total_amount))

    # ---------------------- 5b. payments backfill for historical sales
    payments_t = sa.table(
        "payments",
        sa.column("id", sa.String()),
        sa.column("sale_id", sa.String()),
        sa.column("amount", sa.BigInteger()),
        sa.column("store_id", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    historical = bind.execute(
        sa.select(
            sales_t.c.id,
            sales_t.c.total_amount,
            sales_t.c.store_id,
            sales_t.c.created_at,
        ).where(sales_t.c.total_amount > 0)
    ).all()
    if historical:
        bind.execute(
            sa.insert(payments_t),
            [
                {
                    # hex-32 lowercase — the exact storage format sa.Uuid uses
                    "id": uuid.uuid4().hex,
                    "sale_id": sale_id,
                    "amount": total,
                    "store_id": store_id,
                    "created_at": created_at,
                    "updated_at": created_at,
                }
                for sale_id, total, store_id, created_at in historical
            ],
        )

    # ----------------------------------------- 6. sale_items.price_level
    with op.batch_alter_table("sale_items", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "price_level",
                sa.String(length=16),
                nullable=False,
                server_default="detail",
            )
        )


def downgrade() -> None:
    """Best-effort downgrade. price_tiers rows and per-payment history are
    NOT restorable (that information no longer exists); min_sale_price is
    restored from price_super_gros (they were the same value going up)."""
    bind = op.get_bind()

    with op.batch_alter_table("sale_items", schema=None) as batch_op:
        batch_op.drop_column("price_level")

    with op.batch_alter_table("sales", schema=None) as batch_op:
        batch_op.drop_constraint(
            op.f("fk_sales_customer_id_customers"), type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_sales_customer_id"))
        batch_op.drop_column("paid_amount")
        batch_op.drop_column("customer_id")

    # Restore min_sale_price from the floor, then drop the named prices.
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.add_column(sa.Column("min_sale_price", sa.BigInteger(), nullable=True))
    products_t = sa.table(
        "products",
        sa.column("min_sale_price", sa.BigInteger()),
        sa.column("price_super_gros", sa.BigInteger()),
    )
    bind.execute(
        sa.update(products_t).values(min_sale_price=products_t.c.price_super_gros)
    )
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.alter_column(
            "min_sale_price", existing_type=sa.BigInteger(), nullable=False
        )
        batch_op.drop_constraint(
            op.f("ck_products_price_levels_ordered"), type_="check"
        )
        batch_op.drop_column("low_stock_threshold")
        batch_op.drop_column("image_path")
        batch_op.drop_column("price_super_gros")
        batch_op.drop_column("price_gros")
        batch_op.drop_column("price_detail")

    op.create_table(
        "price_tiers",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("min_quantity", sa.Integer(), nullable=False),
        sa.Column("unit_price", sa.BigInteger(), nullable=False),
        *_base_columns(),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_price_tiers_product_id_products"),
        ),
        sa.ForeignKeyConstraint(
            ["store_id"], ["stores.id"], name=op.f("fk_price_tiers_store_id_stores")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_price_tiers")),
    )
    with op.batch_alter_table("price_tiers", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_price_tiers_product_id"), ["product_id"], unique=False
        )
        batch_op.create_index(
            batch_op.f("ix_price_tiers_store_id"), ["store_id"], unique=False
        )

    with op.batch_alter_table("payments", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_payments_store_id"))
        batch_op.drop_index(batch_op.f("ix_payments_sale_id"))
    op.drop_table("payments")

    with op.batch_alter_table("store_settings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_store_settings_store_id"))
    op.drop_table("store_settings")

    op.drop_index("uq_customers_store_phone_active", table_name="customers")
    with op.batch_alter_table("customers", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_customers_store_id"))
    op.drop_table("customers")
