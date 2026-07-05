"""Phase 8: priced product packagings (cartons).

Revision ID: e5b2c9f4a3d1
Revises: d4f8a1c07e2b
Create Date: 2026-07-04 09:00:00.000000

What this migration does:

1. product_packagings — new table. A packaging is an ADDITIONAL priced sale
   unit of the SAME product (e.g. a carton of 12): its own price triplet
   (détail / gros / super gros, BIGINT cents) plus unit_count = base stock
   units consumed per package. Two DB backstops mirror the service rules:
     - ck_product_packagings_packaging_unit_count_positive  (unit_count >= 1)
     - ck_product_packagings_packaging_price_levels_ordered
       (price_detail >= price_gros AND price_gros >= price_super_gros)
   Indexed on product_id and store_id (both FKs).

2. sale_items — three new snapshot columns so receipts/history survive
   packaging edits and deletes:
     - packaging_id    (nullable FK -> product_packagings.id, indexed)
     - packaging_label (String(80), nullable snapshot of the label)
     - unit_count      (Integer NOT NULL, server_default "1" — base units per
                        sold package). Existing rows get 1, so
                        base_units = quantity * unit_count stays == quantity
                        and every historical financial figure is unchanged.

No data backfill beyond the server_default. downgrade drops all of it.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5b2c9f4a3d1"
down_revision: str | Sequence[str] | None = "d4f8a1c07e2b"
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
    # ---------------------------------------------- 1. product_packagings
    op.create_table(
        "product_packagings",
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("unit_count", sa.Integer(), nullable=False),
        sa.Column("price_detail", sa.BigInteger(), nullable=False),
        sa.Column("price_gros", sa.BigInteger(), nullable=False),
        sa.Column("price_super_gros", sa.BigInteger(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        *_base_columns(),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.CheckConstraint(
            "unit_count >= 1",
            name=op.f("ck_product_packagings_packaging_unit_count_positive"),
        ),
        sa.CheckConstraint(
            "price_detail >= price_gros AND price_gros >= price_super_gros",
            name=op.f("ck_product_packagings_packaging_price_levels_ordered"),
        ),
        sa.ForeignKeyConstraint(
            ["product_id"],
            ["products.id"],
            name=op.f("fk_product_packagings_product_id_products"),
        ),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
            name=op.f("fk_product_packagings_store_id_stores"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_packagings")),
    )
    with op.batch_alter_table("product_packagings", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_product_packagings_product_id"),
            ["product_id"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_product_packagings_store_id"),
            ["store_id"],
            unique=False,
        )

    # ----------------------------------- 2. sale_items packaging snapshots
    with op.batch_alter_table("sale_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("packaging_id", sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column("packaging_label", sa.String(length=80), nullable=True)
        )
        batch_op.add_column(
            sa.Column("unit_count", sa.Integer(), nullable=False, server_default="1")
        )
        batch_op.create_index(
            batch_op.f("ix_sale_items_packaging_id"), ["packaging_id"], unique=False
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_sale_items_packaging_id_product_packagings"),
            "product_packagings",
            ["packaging_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("sale_items", schema=None) as batch_op:
        batch_op.drop_constraint(
            op.f("fk_sale_items_packaging_id_product_packagings"), type_="foreignkey"
        )
        batch_op.drop_index(batch_op.f("ix_sale_items_packaging_id"))
        batch_op.drop_column("unit_count")
        batch_op.drop_column("packaging_label")
        batch_op.drop_column("packaging_id")

    with op.batch_alter_table("product_packagings", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_product_packagings_store_id"))
        batch_op.drop_index(batch_op.f("ix_product_packagings_product_id"))
    op.drop_table("product_packagings")
