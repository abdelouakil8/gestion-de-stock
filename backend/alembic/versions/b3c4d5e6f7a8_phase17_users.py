"""Phase 17: multi-user roles (users table).

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-07-11 13:00:00.000000

users — named local accounts, each with a role (cashier | manager | owner)
and its own PBKDF2 PIN hash. The pre-existing single owner PIN
(settings.pin_hash) keeps working as an owner-level fallback and is migrated
into an owner User on first login, so no install is ever locked out.
"""

import sqlalchemy as sa

from alembic import op

revision = "b3c4d5e6f7a8"
down_revision = "a2b3c4d5e6f7"
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
        "users",
        *_base_columns(),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "role",
            sa.Enum("cashier", "manager", "owner", name="userrole"),
            nullable=False,
        ),
        sa.Column("pin_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_store_id", "users", ["store_id"])

    # Which user rang each sale — a soft reference (no FK), NULL for existing
    # rows. Enables the cashier "own sales only" view.
    op.add_column("sales", sa.Column("created_by_user_id", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("sales", "created_by_user_id")
    op.drop_index("ix_users_store_id", "users")
    op.drop_table("users")
