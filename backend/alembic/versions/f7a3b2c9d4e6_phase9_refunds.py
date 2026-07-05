"""Phase 9: refunds (avoirs) — partial/full returns with stock restoration.

Revision ID: f7a3b2c9d4e6
Revises: e5b2c9f4a3d1
Create Date: 2026-07-05 09:00:00.000000

What this migration does:

1. refunds — header table for a return operation. One refund per sale is the
   common case, but multiple partial refunds are allowed.
   - sale_id FK -> sales.id (indexed)
   - reason (TEXT, nullable — operator-optional description)
   - total_amount (BIGINT cents via Money TypeDecorator)
   Standard BaseModel columns: id, created_at, updated_at, deleted_at,
   is_synced, synced_at, store_id.

2. refund_items — individual returned lines referencing the original sale_item.
   - refund_id FK -> refunds.id (indexed)
   - sale_item_id FK -> sale_items.id (indexed)
   - quantity (INTEGER NOT NULL — packages/units returned)
   - unit_count (INTEGER NOT NULL, default 1 — base units per package snapshot)
   - unit_price_refunded (BIGINT cents — snapshot of original price)
   - line_total (BIGINT cents — qty × unit_price)
   Standard BaseModel + StoreScopedMixin columns.

No data backfill. downgrade drops both tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f7a3b2c9d4e6"
down_revision: str | None = "e5b2c9f4a3d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "refunds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("sale_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("total_amount", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_synced", sa.Boolean(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_refunds"),
        sa.ForeignKeyConstraint(
            ["store_id"], ["stores.id"], name="fk_refunds_store_id_stores"
        ),
        sa.ForeignKeyConstraint(
            ["sale_id"], ["sales.id"], name="fk_refunds_sale_id_sales"
        ),
    )
    op.create_index("ix_refunds_sale_id", "refunds", ["sale_id"])
    op.create_index("ix_refunds_store_id", "refunds", ["store_id"])

    op.create_table(
        "refund_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("refund_id", sa.Uuid(), nullable=False),
        sa.Column("sale_item_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("unit_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("unit_price_refunded", sa.BigInteger(), nullable=False),
        sa.Column("line_total", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_synced", sa.Boolean(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_refund_items"),
        sa.ForeignKeyConstraint(
            ["store_id"], ["stores.id"], name="fk_refund_items_store_id_stores"
        ),
        sa.ForeignKeyConstraint(
            ["refund_id"], ["refunds.id"], name="fk_refund_items_refund_id_refunds"
        ),
        sa.ForeignKeyConstraint(
            ["sale_item_id"],
            ["sale_items.id"],
            name="fk_refund_items_sale_item_id_sale_items",
        ),
    )
    op.create_index("ix_refund_items_refund_id", "refund_items", ["refund_id"])
    op.create_index("ix_refund_items_sale_item_id", "refund_items", ["sale_item_id"])
    op.create_index("ix_refund_items_store_id", "refund_items", ["store_id"])


def downgrade() -> None:
    op.drop_table("refund_items")
    op.drop_table("refunds")
