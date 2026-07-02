import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, StoreScopedMixin
from app.db.types import Money

if TYPE_CHECKING:
    from app.models.product import Product


class Sale(BaseModel, StoreScopedMixin):
    """Finalized sale — an immutable financial record (soft delete only)."""

    __tablename__ = "sales"

    total_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)

    # No delete/delete-orphan cascade: sale items are financial records and
    # must never be hard-deleted, not even by accidental collection removal.
    items: Mapped[list["SaleItem"]] = relationship(back_populates="sale")


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
    unit_price_applied: Mapped[Decimal] = mapped_column(Money, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Money, nullable=False)

    sale: Mapped["Sale"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()
