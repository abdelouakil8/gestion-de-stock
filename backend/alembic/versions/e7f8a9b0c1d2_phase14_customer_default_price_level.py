"""Phase 14: per-customer default price level.

Revision ID: e7f8a9b0c1d2
Revises: d5e6f7a8b9c0
Create Date: 2026-07-11 10:00:00.000000

Adds an optional ``default_price_level`` to customers ("detail" | "gros" |
"super_gros"). NULL = no preference (every existing row), so attaching a
customer at the caisse only overrides line pricing when they carry an
explicit preference. Value validation lives in the schema, never here.
"""

import sqlalchemy as sa

from alembic import op

revision = "e7f8a9b0c1d2"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column("default_price_level", sa.String(length=16), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("customers", "default_price_level")
