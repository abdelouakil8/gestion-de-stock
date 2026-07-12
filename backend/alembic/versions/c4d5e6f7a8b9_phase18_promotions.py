"""Phase 18: promotion codes + line/coupon discounts.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-07-11 14:00:00.000000

promotions — store-scoped coupon codes (percent | fixed), time-boxed and
optionally use-capped (used_count incremented atomically at checkout). The
sales table gains promo_code + promo_discount so a redeemed coupon is recorded
on the sale (total_amount is already net of it).
"""

import sqlalchemy as sa

from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "b3c4d5e6f7a8"
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
        "promotions",
        *_base_columns(),
        sa.Column("store_id", sa.Uuid(), sa.ForeignKey("stores.id"), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column(
            "type", sa.Enum("percent", "fixed", name="promotiontype"), nullable=False
        ),
        sa.Column("value", sa.BigInteger(), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("max_uses", sa.Integer(), nullable=True),
        sa.Column("used_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")
        ),
        sa.PrimaryKeyConstraint("id", name="pk_promotions"),
    )
    op.create_index("ix_promotions_store_id", "promotions", ["store_id"])
    op.create_index("ix_promotions_code", "promotions", ["code"])

    op.add_column("sales", sa.Column("promo_code", sa.String(length=40), nullable=True))
    op.add_column(
        "sales",
        sa.Column(
            "promo_discount", sa.BigInteger(), nullable=False, server_default="0"
        ),
    )


def downgrade() -> None:
    op.drop_column("sales", "promo_discount")
    op.drop_column("sales", "promo_code")
    op.drop_index("ix_promotions_code", "promotions")
    op.drop_index("ix_promotions_store_id", "promotions")
    op.drop_table("promotions")
