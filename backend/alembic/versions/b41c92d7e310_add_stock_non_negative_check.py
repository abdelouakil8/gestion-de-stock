"""add stock non-negative check constraint

Revision ID: b41c92d7e310
Revises: a70e8f6fcbd9
Create Date: 2026-07-02 20:15:00.000000

DB-level backstop for the inventory rule: stock can never go negative,
regardless of application code. Batch mode rebuilds the table on SQLite.
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b41c92d7e310"
down_revision: str | Sequence[str] | None = "a70e8f6fcbd9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.create_check_constraint(
            "stock_quantity_non_negative", "stock_quantity >= 0"
        )


def downgrade() -> None:
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.drop_constraint(
            op.f("ck_products_stock_quantity_non_negative"), type_="check"
        )
