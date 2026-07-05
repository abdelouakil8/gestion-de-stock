"""Phase 10: sequential invoice numbers, line discounts, payment methods.

Revision ID: a1b2c3d4e5f6
Revises: f7a3b2c9d4e6
Create Date: 2026-07-05 12:00:00.000000

What this migration does:

1. sale_sequences — per-store-per-year atomic counter for gapless invoice
   numbering. The sequence is incremented via a conditional UPDATE in the
   checkout service (same race-safety pattern as decrement_stock).

2. sales.invoice_number — sequential integer (nullable initially while we
   backfill existing rows, then we leave it nullable for safety since
   SQLite ALTER TABLE cannot add NOT NULL to existing data without a
   full table rebuild). New sales always get one; the backfill below
   assigns numbers in created_at order per store.

3. sale_items.discount_amount — BIGINT cents (Money), default 0. A
   per-line discount separate from the applied unit price. line_total =
   (unit_price * qty) - discount_amount. The effective per-unit price
   after discount is still floor-checked (never below super_gros).

4. payments.payment_method — VARCHAR(16), default "cash". Tracks how
   the payment was made (cash/card/mobile/other) for reconciliation.

Backfill: existing sales get invoice_number assigned sequentially by
created_at per store. Existing sale_items get discount_amount=0.
Existing payments get payment_method="cash".
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f7a3b2c9d4e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Sale sequences table.
    op.create_table(
        "sale_sequences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False, server_default="0"),
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
        sa.PrimaryKeyConstraint("id", name="pk_sale_sequences"),
        sa.ForeignKeyConstraint(
            ["store_id"], ["stores.id"], name="fk_sale_sequences_store_id_stores"
        ),
        sa.UniqueConstraint("store_id", "year", name="uq_sale_sequences_store_year"),
    )

    # 2. Invoice number on sales (nullable — backfilled below).
    with op.batch_alter_table("sales") as batch_op:
        batch_op.add_column(sa.Column("invoice_number", sa.Integer(), nullable=True))

    # 3. Discount on sale_items.
    with op.batch_alter_table("sale_items") as batch_op:
        batch_op.add_column(
            sa.Column(
                "discount_amount",
                sa.BigInteger(),
                nullable=False,
                server_default="0",
            )
        )

    # 4. Payment method on payments.
    with op.batch_alter_table("payments") as batch_op:
        batch_op.add_column(
            sa.Column(
                "payment_method",
                sa.String(16),
                nullable=False,
                server_default="cash",
            )
        )

    # Backfill: assign invoice numbers sequentially per store.
    conn = op.get_bind()
    stores = conn.execute(sa.text("SELECT id FROM stores")).fetchall()
    for (store_id,) in stores:
        sales = conn.execute(
            sa.text(
                "SELECT id FROM sales WHERE store_id = :sid "
                "AND deleted_at IS NULL ORDER BY created_at ASC"
            ),
            {"sid": store_id},
        ).fetchall()
        for i, (sale_id,) in enumerate(sales, start=1):
            conn.execute(
                sa.text("UPDATE sales SET invoice_number = :num WHERE id = :sid"),
                {"num": i, "sid": sale_id},
            )
        if sales:
            import uuid

            year_val = conn.execute(
                sa.text(
                    "SELECT strftime('%Y', created_at) FROM sales "
                    "WHERE store_id = :sid AND deleted_at IS NULL "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"sid": store_id},
            ).scalar()
            year_int = int(year_val) if year_val else 2026
            conn.execute(
                sa.text(
                    "INSERT INTO sale_sequences (id, store_id, year, last_number) "
                    "VALUES (:id, :sid, :yr, :num)"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "sid": store_id,
                    "yr": year_int,
                    "num": len(sales),
                },
            )


def downgrade() -> None:
    with op.batch_alter_table("payments") as batch_op:
        batch_op.drop_column("payment_method")
    with op.batch_alter_table("sale_items") as batch_op:
        batch_op.drop_column("discount_amount")
    with op.batch_alter_table("sales") as batch_op:
        batch_op.drop_column("invoice_number")
    op.drop_table("sale_sequences")
