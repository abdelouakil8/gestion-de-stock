import uuid
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, StoreScopedMixin
from app.db.types import Money


class PurchaseOrder(BaseModel, StoreScopedMixin):
    """A goods purchase from a supplier — mirrors Sale's bookkeeping."""

    __tablename__ = "purchase_orders"

    supplier_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("suppliers.id"), nullable=False, index=True
    )
    total_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(
        Money, nullable=False, default=Decimal("0.00")
    )
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="received", server_default="received"
    )

    items: Mapped[list["PurchaseOrderItem"]] = relationship(
        back_populates="order"
    )
    payments: Mapped[list["SupplierPayment"]] = relationship(
        back_populates="order", order_by="SupplierPayment.created_at"
    )
    supplier: Mapped["Supplier"] = relationship()  # noqa: F821

    @property
    def balance(self) -> Decimal:
        return self.total_amount - self.paid_amount


class PurchaseOrderItem(BaseModel, StoreScopedMixin):
    """One product line of a purchase order."""

    __tablename__ = "purchase_order_items"

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("purchase_orders.id"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Money, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Money, nullable=False)

    order: Mapped["PurchaseOrder"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()  # noqa: F821


class SupplierPayment(BaseModel, StoreScopedMixin):
    """Append-only payment to a supplier — mirrors Payment exactly."""

    __tablename__ = "supplier_payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="supplier_payment_positive"),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("purchase_orders.id"), nullable=False, index=True
    )
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    payment_method: Mapped[str] = mapped_column(
        String(16), nullable=False, default="cash", server_default="cash"
    )

    order: Mapped["PurchaseOrder"] = relationship(back_populates="payments")
