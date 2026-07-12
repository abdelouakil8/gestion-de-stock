"""Stock movement ledger — append-only record of every inventory change.

Each row captures what happened (type), how many units moved (quantity_delta),
the resulting stock level (quantity_after), and a foreign reference to the
originating document (sale, purchase order, refund, or None for adjustments).

Rows are never updated or deleted after creation — the ledger is immutable.
"""

import uuid
from enum import StrEnum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel, StoreScopedMixin


class MovementType(StrEnum):
    sale = "sale"
    purchase = "purchase"
    refund = "refund"
    adjustment = "adjustment"


class StockMovement(BaseModel, StoreScopedMixin):
    __tablename__ = "stock_movements"

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id"), nullable=False
    )
    movement_type: Mapped[MovementType] = mapped_column(
        SAEnum(MovementType, name="movementtype"), nullable=False
    )
    quantity_delta: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_after: Mapped[int] = mapped_column(Integer, nullable=False)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # Structured motive for manual adjustments (inventaire / perte / casse /
    # correction / autre). NULL for automatic movements (sale/purchase/refund).
    reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<StockMovement id={self.id} product_id={self.product_id} "
            f"type={self.movement_type} delta={self.quantity_delta}>"
        )
