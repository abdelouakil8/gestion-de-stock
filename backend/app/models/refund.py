"""Refund (avoir) — partial or full return against a finalized sale.

A refund is an IMMUTABLE financial record: once created it is never modified
or deleted. Stock is atomically restored at creation time. Multiple partial
refunds per sale are allowed as long as the cumulative refunded quantity per
item never exceeds the originally sold quantity.
"""

import uuid
from decimal import Decimal

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, StoreScopedMixin
from app.db.types import Money


class Refund(BaseModel, StoreScopedMixin):
    """Header of one refund operation against a sale."""

    __tablename__ = "refunds"

    sale_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sales.id"), nullable=False, index=True
    )
    reason: Mapped[str | None] = mapped_column(Text, default=None)
    total_amount: Mapped[Decimal] = mapped_column(Money, nullable=False)

    items: Mapped[list["RefundItem"]] = relationship(back_populates="refund")


class RefundItem(BaseModel, StoreScopedMixin):
    """One returned product line within a refund."""

    __tablename__ = "refund_items"

    refund_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("refunds.id"), nullable=False, index=True
    )
    sale_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("sale_items.id"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(nullable=False)
    unit_count: Mapped[int] = mapped_column(nullable=False, default=1)
    unit_price_refunded: Mapped[Decimal] = mapped_column(Money, nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Money, nullable=False)

    refund: Mapped["Refund"] = relationship(back_populates="items")
