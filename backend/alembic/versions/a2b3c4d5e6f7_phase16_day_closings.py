"""Phase 16: daily cash-register closings (clôture de caisse).

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
Create Date: 2026-07-11 12:30:00.000000

day_closings — one signed reconciliation record per store per calendar day.
It snapshots the automatic day summary (sales count, revenue, the payment
split, discounts, refunds), the operator's physical cash count, the expected
cash and the computed gap. A UNIQUE (store_id, closing_date) makes a day
closable exactly once. Money columns are BIGINT minor units (the app's Money
type); the gap column is intentionally signed (a shortfall is negative).
"""

import sqlalchemy as sa

from alembic import op

revision = "a2b3c4d5e6f7"
down_revision = "f1a2b3c4d5e6"
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
        "day_closings",
        *_base_columns(),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("closing_date", sa.Date(), nullable=False),
        sa.Column("sales_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_revenue", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("cash_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("card_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "transfer_total", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("other_total", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "total_discounts", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("total_refunds", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("expected_cash", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column(
            "physical_cash_count", sa.BigInteger(), nullable=False, server_default="0"
        ),
        sa.Column("gap", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_day_closings"),
        sa.UniqueConstraint("store_id", "closing_date", name="day_closings_store_date"),
    )
    op.create_index("ix_day_closings_store_id", "day_closings", ["store_id"])
    op.create_index("ix_day_closings_closing_date", "day_closings", ["closing_date"])


def downgrade() -> None:
    op.drop_index("ix_day_closings_closing_date", "day_closings")
    op.drop_index("ix_day_closings_store_id", "day_closings")
    op.drop_table("day_closings")
