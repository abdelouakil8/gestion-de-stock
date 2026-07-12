"""Daily cash-register closing (clôture de caisse) — one signed record per
store per calendar day reconciling the theoretical takings against the cash
physically counted in the drawer.

The row snapshots the automatic day summary (sales count, revenue, the
payment-method split, discounts, refunds) alongside the operator's physical
count and the computed gap, so a closing is a self-contained audit document
that never has to be recomputed from moving data.

A unique (store_id, closing_date) index makes a day closable exactly once.
"""

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel, StoreScopedMixin
from app.db.types import Money


class DayClosing(BaseModel, StoreScopedMixin):
    __tablename__ = "day_closings"
    __table_args__ = (
        UniqueConstraint("store_id", "closing_date", name="day_closings_store_date"),
    )

    # The calendar day (store-local) being closed.
    closing_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # --- Section A: automatic summary, snapshotted at closing time. ---
    sales_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_revenue: Mapped[Decimal] = mapped_column(
        Money, nullable=False, default=Decimal("0.00")
    )
    cash_total: Mapped[Decimal] = mapped_column(
        Money, nullable=False, default=Decimal("0.00")
    )
    card_total: Mapped[Decimal] = mapped_column(
        Money, nullable=False, default=Decimal("0.00")
    )
    transfer_total: Mapped[Decimal] = mapped_column(
        Money, nullable=False, default=Decimal("0.00")
    )
    other_total: Mapped[Decimal] = mapped_column(
        Money, nullable=False, default=Decimal("0.00")
    )
    total_discounts: Mapped[Decimal] = mapped_column(
        Money, nullable=False, default=Decimal("0.00")
    )
    total_refunds: Mapped[Decimal] = mapped_column(
        Money, nullable=False, default=Decimal("0.00")
    )

    # --- Section B: physical count + reconciliation. ---
    # Theoretical cash the drawer should hold = cash_total - total_refunds.
    expected_cash: Mapped[Decimal] = mapped_column(
        Money, nullable=False, default=Decimal("0.00")
    )
    physical_cash_count: Mapped[Decimal] = mapped_column(
        Money, nullable=False, default=Decimal("0.00")
    )
    # Signed gap = physical - expected (Money is >= 0 in the schema layer but
    # the DB column itself is a plain integer of minor units, so it can go
    # negative here — a shortfall).
    gap: Mapped[Decimal] = mapped_column(Money, nullable=False, default=Decimal("0.00"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<DayClosing store_id={self.store_id} date={self.closing_date} "
            f"gap={self.gap}>"
        )
