"""Phase 12: stock movement ledger.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-07-10 10:00:00.000000

What this migration does:

1. stock_movements — append-only log of every inventory change (sales,
   purchases, refunds, manual adjustments). Each row records the type,
   signed quantity delta, resulting stock snapshot, an optional foreign
   reference UUID (sale_id / purchase_order_id / refund_id), and a free-text
   note for manual adjustments.

Indexes:
  - (store_id, product_id)  — fast per-product history within a store
  - (product_id, created_at) — time-ordered queries for a single product
"""

import sqlalchemy as sa

from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_synced", sa.Boolean(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "stock_movements",
        *_base_columns(),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column(
            "product_id", sa.Uuid(), sa.ForeignKey("products.id"), nullable=False
        ),
        sa.Column(
            "movement_type",
            sa.Enum("sale", "purchase", "refund", "adjustment", name="movementtype"),
            nullable=False,
        ),
        sa.Column("quantity_delta", sa.Integer(), nullable=False),
        sa.Column("quantity_after", sa.Integer(), nullable=False),
        sa.Column("reference_id", sa.Uuid(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_stock_movements"),
    )
    op.create_index(
        "ix_stock_movements_store_product",
        "stock_movements",
        ["store_id", "product_id"],
    )
    op.create_index(
        "ix_stock_movements_product_created_at",
        "stock_movements",
        ["product_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_stock_movements_product_created_at", "stock_movements")
    op.drop_index("ix_stock_movements_store_product", "stock_movements")
    op.drop_table("stock_movements")
