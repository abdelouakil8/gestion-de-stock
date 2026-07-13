"""Phase 20: performance indexes for hot query paths.

Revision ID: e8f9a0b1c2d3
Revises: d5e6f7a8b9c1
Create Date: 2026-07-13 12:00:00.000000

Adds composite indexes that speed up the most common query patterns:
statistics date-range scans, stock-movement lookups, outstanding-credit
filters, and purchase-order supplier+date queries.
"""

from alembic import op

revision = "e8f9a0b1c2d3"
down_revision = "d5e6f7a8b9c1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "ix_sales_store_created",
        "sales",
        ["store_id", "created_at"],
    )
    op.create_index(
        "ix_sales_store_customer",
        "sales",
        ["store_id", "customer_id"],
    )
    op.create_index(
        "ix_sale_items_product_sale",
        "sale_items",
        ["product_id", "sale_id"],
    )
    op.create_index(
        "ix_stock_movements_product_created",
        "stock_movements",
        ["product_id", "created_at"],
    )
    op.create_index(
        "ix_payments_sale_created",
        "payments",
        ["sale_id", "created_at"],
    )
    op.create_index(
        "ix_purchase_orders_supplier_created",
        "purchase_orders",
        ["supplier_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_purchase_orders_supplier_created", table_name="purchase_orders")
    op.drop_index("ix_payments_sale_created", table_name="payments")
    op.drop_index("ix_stock_movements_product_created", table_name="stock_movements")
    op.drop_index("ix_sale_items_product_sale", table_name="sale_items")
    op.drop_index("ix_sales_store_customer", table_name="sales")
    op.drop_index("ix_sales_store_created", table_name="sales")
