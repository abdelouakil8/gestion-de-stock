"""Phase 15: structured reason on stock movements.

Revision ID: f1a2b3c4d5e6
Revises: e7f8a9b0c1d2
Create Date: 2026-07-11 12:00:00.000000

Adds an optional ``reason`` to stock_movements — a short machine code for the
motive of a MANUAL adjustment (inventaire physique / perte / casse /
correction / autre). NULL for every automatic movement (sale/purchase/refund)
and every existing row. The free-text ``note`` stays for the operator's extra
comment; the two are complementary.
"""

import sqlalchemy as sa

from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "stock_movements",
        sa.Column("reason", sa.String(length=32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("stock_movements", "reason")
