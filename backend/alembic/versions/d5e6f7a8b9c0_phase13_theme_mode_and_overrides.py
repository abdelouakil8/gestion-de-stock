"""Phase 13: theme mode + custom color overrides.

Revision ID: d5e6f7a8b9c0
Revises: c3d4e5f6a7b8
Create Date: 2026-07-10 19:00:00.000000

Adds per-store theme controls to store_settings:

1. theme_mode ("light" | "dark") — NOT NULL, defaults to "light" so every
   existing row keeps the current appearance.
2. theme_bg / theme_surface / theme_text / theme_border — optional structural
   color overrides (hex). NULL = use the mode default; a hex value overrides
   that single role. Validation (mode whitelist, hex format) lives in the
   schema, never here.
"""

import sqlalchemy as sa

from alembic import op

revision = "d5e6f7a8b9c0"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "store_settings",
        sa.Column(
            "theme_mode",
            sa.String(length=5),
            nullable=False,
            server_default="light",
        ),
    )
    for column in ("theme_bg", "theme_surface", "theme_text", "theme_border"):
        op.add_column(
            "store_settings", sa.Column(column, sa.String(length=7), nullable=True)
        )


def downgrade() -> None:
    for column in ("theme_border", "theme_text", "theme_surface", "theme_bg"):
        op.drop_column("store_settings", column)
    op.drop_column("store_settings", "theme_mode")
