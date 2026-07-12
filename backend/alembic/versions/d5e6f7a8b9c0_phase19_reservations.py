"""Phase 19: product reservations (layaway) + reserved stock.

Revision ID: d5e6f7a8b9c1
Revises: c4d5e6f7a8b9
Create Date: 2026-07-11 15:00:00.000000

products.reserved_quantity holds units set aside by active reservations
(available = stock_quantity - reserved_quantity). reservations +
reservation_items store the layaway header/lines. A reservation holds stock
without decrementing it; completing it converts the lines into a Sale.
"""

import sqlalchemy as sa

from alembic import op

# NB: the file slug ends d5e6f7a8b9c0 but the actual revision id is unique
# below (the phase-13 migration already used d5e6f7a8b9c0).
revision = "d5e6f7a8b9c1"
down_revision = "c4d5e6f7a8b9"
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
    op.add_column(
        "products",
        sa.Column(
            "reserved_quantity",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )

    op.create_table(
        "reservations",
        *_base_columns(),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column(
            "customer_id", sa.Uuid(), sa.ForeignKey("customers.id"), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "completed", "cancelled", name="reservationstatus"),
            nullable=False,
        ),
        sa.Column(
            "deposit_amount", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("sale_id", sa.Uuid(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_reservations"),
    )
    op.create_index("ix_reservations_store_id", "reservations", ["store_id"])
    op.create_index("ix_reservations_customer_id", "reservations", ["customer_id"])

    op.create_table(
        "reservation_items",
        *_base_columns(),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column(
            "reservation_id",
            sa.Uuid(),
            sa.ForeignKey("reservations.id"),
            nullable=False,
        ),
        sa.Column(
            "product_id", sa.Uuid(), sa.ForeignKey("products.id"), nullable=False
        ),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column(
            "price_level", sa.String(length=16), nullable=False, server_default="detail"
        ),
        sa.Column("unit_price_snapshot", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_reservation_items"),
    )
    op.create_index(
        "ix_reservation_items_reservation_id",
        "reservation_items",
        ["reservation_id"],
    )
    op.create_index(
        "ix_reservation_items_product_id", "reservation_items", ["product_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_reservation_items_product_id", "reservation_items")
    op.drop_index("ix_reservation_items_reservation_id", "reservation_items")
    op.drop_table("reservation_items")
    op.drop_index("ix_reservations_customer_id", "reservations")
    op.drop_index("ix_reservations_store_id", "reservations")
    op.drop_table("reservations")
    op.drop_column("products", "reserved_quantity")
