# NOTE: This model is retained for database schema integrity only.
# The reservations feature has been removed from the application.
# Do NOT use this model in any new code. The table is kept to avoid
# data loss on existing installations.

"""Product reservations (layaway / mise de côté).

A reservation HOLDS stock (via Product.reserved_quantity) for a customer
without decrementing it, records an optional deposit, and expires on a date.
Completing it converts the held items into a Sale (through finalize_sale) and
releases the hold; cancelling releases the hold and restores availability.
Reservation items snapshot the price level + unit price at reservation time.
"""

import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, StoreScopedMixin
from app.db.types import Money

if TYPE_CHECKING:
    from app.models.product import Product


class ReservationStatus(StrEnum):
    active = "active"
    completed = "completed"
    cancelled = "cancelled"


class Reservation(BaseModel, StoreScopedMixin):
    __tablename__ = "reservations"

    # A reservation always belongs to a customer (recoverable, contactable).
    customer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("customers.id"), nullable=False, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    status: Mapped[ReservationStatus] = mapped_column(
        SAEnum(ReservationStatus, name="reservationstatus"),
        nullable=False,
        default=ReservationStatus.active,
    )
    deposit_amount: Mapped[Decimal] = mapped_column(
        Money, nullable=False, default=Decimal("0.00")
    )
    notes: Mapped[str | None] = mapped_column(Text, default=None)
    # Set when completed → the Sale it produced.
    sale_id: Mapped[uuid.UUID | None] = mapped_column(default=None)

    items: Mapped[list["ReservationItem"]] = relationship(back_populates="reservation")

    def __repr__(self) -> str:
        return f"<Reservation id={self.id} status={self.status}>"


class ReservationItem(BaseModel, StoreScopedMixin):
    __tablename__ = "reservation_items"

    reservation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("reservations.id"), nullable=False, index=True
    )
    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    quantity: Mapped[int] = mapped_column(nullable=False)
    price_level: Mapped[str] = mapped_column(
        String(16), nullable=False, default="detail"
    )
    # Price snapshot at reservation time (display only; the sale re-resolves
    # and re-checks the floor at completion).
    unit_price_snapshot: Mapped[Decimal] = mapped_column(Money, nullable=False)

    reservation: Mapped["Reservation"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()
