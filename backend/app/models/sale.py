import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, StoreScopedMixin
from app.db.types import Money

if TYPE_CHECKING:
    from app.models.customer import Customer
    from app.models.product import Product


class Sale(BaseModel, StoreScopedMixin):
    """Finalized sale — an immutable financial record (soft delete only)."""

    __tablename__ = "sales"

    total_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    # Walk-in sales stay anonymous; credit (partially paid) sales MUST carry
    # a customer — the rule is enforced in the checkout service.
    customer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("customers.id"), index=True, default=None
    )
    # Set when a walk-in (customer_id NULL) sale is intentionally kept
    # anonymous — the operator's explicit "leave anonymous" choice.
    guest_confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    # Cache of SUM(payments.amount), recomputed transactionally by the
    # payments service on every write — the payments table is the single
    # source of truth, this column only mirrors it for cheap SQL filters.
    paid_amount: Mapped[Decimal] = mapped_column(
        Money, nullable=False, default=Decimal("0.00")
    )
    invoice_number: Mapped[int | None] = mapped_column(nullable=True, default=None)

    # No delete/delete-orphan cascade: sale items and payments are financial
    # records and must never be hard-deleted, not even by accidental
    # collection removal.
    items: Mapped[list["SaleItem"]] = relationship(back_populates="sale")
    payments: Mapped[list["Payment"]] = relationship(
        back_populates="sale", order_by="Payment.created_at"
    )
    customer: Mapped["Customer | None"] = relationship()

    @property
    def balance(self) -> Decimal:
        """Outstanding amount — pure derivation, no business logic."""
        return self.total_amount - self.paid_amount


class SaleItem(BaseModel, StoreScopedMixin):
    """One product line of a sale, with the price that was actually applied."""

    __tablename__ = "sale_items"

    sale_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales.id"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(nullable=False)
    # Which named price level the cashier picked ("detail" | "gros" |
    # "super_gros") — the server resolved unit_price_applied from it.
    price_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default="detail"
    )
    # Optional priced packaging (carton) sold on this line. quantity keeps
    # meaning "number of packages"; unit_count is the base stock units each
    # package consumed (snapshot). base_units of the line = quantity *
    # unit_count. packaging_label snapshots the label so receipts/history
    # survive packaging edits/deletes.
    packaging_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("product_packagings.id"), index=True, default=None
    )
    packaging_label: Mapped[str | None] = mapped_column(String(80), default=None)
    unit_count: Mapped[int] = mapped_column(
        nullable=False, default=1, server_default="1"
    )
    unit_price_applied: Mapped[Decimal] = mapped_column(Money, nullable=False)
    discount_amount: Mapped[Decimal] = mapped_column(
        Money, nullable=False, default=Decimal("0.00"), server_default="0"
    )
    line_total: Mapped[Decimal] = mapped_column(Money, nullable=False)

    sale: Mapped["Sale"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()


class Payment(BaseModel, StoreScopedMixin):
    """One payment received against a sale — auditable, append-only.

    The payment made at checkout is a row here too, so the full payment
    history of a credit sale can always be reconstructed.
    """

    __tablename__ = "payments"
    __table_args__ = (CheckConstraint("amount > 0", name="amount_positive"),)

    sale_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales.id"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    payment_method: Mapped[str] = mapped_column(
        String(16), nullable=False, default="cash", server_default="cash"
    )

    sale: Mapped["Sale"] = relationship(back_populates="payments")
