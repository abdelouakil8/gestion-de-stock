"""Phase 7: precomputed search_text + intentional-guest confirmation.

Revision ID: d4f8a1c07e2b
Revises: c9a1e4b7d2f0
Create Date: 2026-07-03 21:00:00.000000

What this migration does (backfills run in Python on the connection, so the
same code works on SQLite today and PostgreSQL later):

1. products.search_text / customers.search_text — new String(400) NOT NULL
   columns (server_default '') holding a precomputed, normalized search key
   (NFKC + casefold + accent/tashkeel folding + Arabic letter folding). The
   smart-search service prefilters and re-ranks against this column instead
   of the raw name/phone, so accented French and Arabic queries match. The
   backfill uses the SAME app.core.textnorm.normalize_text function the
   services call at write-time, guaranteeing stored values stay canonical.
     products : normalize_text(name + " " + (barcode or ""))
     customers: normalize_text(name + " " + phone + " " + (note or ""))

2. sales.guest_confirmed_at — new nullable timestamp. NULL + NULL customer =
   a walk-in sale still "to resolve"; a set timestamp = the operator's
   explicit "leave anonymous" decision. Existing walk-in sales (customer_id
   IS NULL) are backfilled to their own created_at: history is accepted as
   intentionally anonymous so the resolution queue starts with new sales
   only, and created_at keeps the mark auditable. Sales that already carry a
   customer keep guest_confirmed_at NULL.

The opaque-key rule from phase 6 applies again: id columns in table
reflections are raw sa.String() so the Uuid type cannot rewrite them (lower
hex) and make WHERE clauses silently match nothing.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op
from app.core.textnorm import normalize_text

# revision identifiers, used by Alembic.
revision: str = "d4f8a1c07e2b"
down_revision: str | Sequence[str] | None = "c9a1e4b7d2f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    # ------------------------------------------ 1. new search_text columns
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "search_text",
                sa.String(length=400),
                nullable=False,
                server_default="",
            )
        )
    with op.batch_alter_table("customers", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "search_text",
                sa.String(length=400),
                nullable=False,
                server_default="",
            )
        )

    # -------------------------------------- 2. new sales.guest_confirmed_at
    with op.batch_alter_table("sales", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "guest_confirmed_at", sa.DateTime(timezone=True), nullable=True
            )
        )

    # ------------------------------------------- backfill products.search_text
    # Raw String ids: opaque keys must pass through untouched (see docstring).
    products_t = sa.table(
        "products",
        sa.column("id", sa.String()),
        sa.column("name", sa.String()),
        sa.column("barcode", sa.String()),
        sa.column("search_text", sa.String()),
    )
    for product_id, name, barcode in bind.execute(
        sa.select(products_t.c.id, products_t.c.name, products_t.c.barcode)
    ).all():
        value = normalize_text(f"{name or ''} {barcode or ''}")
        bind.execute(
            sa.update(products_t)
            .where(products_t.c.id == product_id)
            .values(search_text=value)
        )

    # ------------------------------------------ backfill customers.search_text
    customers_t = sa.table(
        "customers",
        sa.column("id", sa.String()),
        sa.column("name", sa.String()),
        sa.column("phone", sa.String()),
        sa.column("note", sa.String()),
        sa.column("search_text", sa.String()),
    )
    for customer_id, name, phone, note in bind.execute(
        sa.select(
            customers_t.c.id,
            customers_t.c.name,
            customers_t.c.phone,
            customers_t.c.note,
        )
    ).all():
        value = normalize_text(f"{name or ''} {phone or ''} {note or ''}")
        bind.execute(
            sa.update(customers_t)
            .where(customers_t.c.id == customer_id)
            .values(search_text=value)
        )

    # --------------------------- backfill guest_confirmed_at for walk-in sales
    # Existing anonymous sales are treated as intentionally anonymous as of
    # their own creation time — the resolution queue only fills with new
    # sales going forward. Sales with a customer stay NULL.
    sales_t = sa.table(
        "sales",
        sa.column("id", sa.String()),
        sa.column("customer_id", sa.String()),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("guest_confirmed_at", sa.DateTime(timezone=True)),
    )
    bind.execute(
        sa.update(sales_t)
        .where(sales_t.c.customer_id.is_(None))
        .values(guest_confirmed_at=sales_t.c.created_at)
    )


def downgrade() -> None:
    """Drop the three structural columns. The normalized search_text values
    are not restorable (they are derived, not source data), but they are
    trivially recomputable by re-running the upgrade."""
    with op.batch_alter_table("sales", schema=None) as batch_op:
        batch_op.drop_column("guest_confirmed_at")
    with op.batch_alter_table("customers", schema=None) as batch_op:
        batch_op.drop_column("search_text")
    with op.batch_alter_table("products", schema=None) as batch_op:
        batch_op.drop_column("search_text")
