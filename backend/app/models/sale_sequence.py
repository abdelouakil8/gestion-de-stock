"""Per-store-per-year invoice number counter — atomic, gapless."""

import uuid

from sqlalchemy import ForeignKey, Integer, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SaleSequence(Base):
    """Atomic counter for sequential invoice numbers.

    One row per (store_id, year). The checkout service increments
    last_number with a conditional UPDATE — same race-safety pattern
    as decrement_stock.
    """

    __tablename__ = "sale_sequences"
    __table_args__ = (
        UniqueConstraint("store_id", "year", name="uq_sale_sequences_store_year"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    store_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stores.id"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    last_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
