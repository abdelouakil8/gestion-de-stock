"""Schemas for the daily cash-register closing (clôture de caisse)."""

from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Money, ReadSchema


class DaySummary(BaseModel):
    """Section A — the automatic day recap the operator reconciles against.

    ``already_closed`` tells the UI whether this calendar day already has a
    persisted closing (so the button can show "Clôture effectuée")."""

    date: date
    sales_count: int
    total_revenue: Money
    cash_total: Money
    card_total: Money
    transfer_total: Money
    other_total: Money
    total_discounts: Money
    total_refunds: Money
    # Theoretical cash left in the drawer = cash takings - cash refunds.
    expected_cash: Money
    already_closed: bool = False


class DayClosingCreate(BaseModel):
    """Body of POST /sales/close-day."""

    store_id: UUID
    date: date
    physical_cash_count: Money = Field(default=Decimal("0.00"))
    notes: str | None = Field(default=None, max_length=1000)


class DayClosingRead(ReadSchema):
    store_id: UUID
    closing_date: date
    sales_count: int
    total_revenue: Money
    cash_total: Money
    card_total: Money
    transfer_total: Money
    other_total: Money
    total_discounts: Money
    total_refunds: Money
    expected_cash: Money
    physical_cash_count: Money
    # Signed: a shortfall is negative, so this is a plain Decimal (not Money,
    # which is constrained to >= 0 at the schema boundary).
    gap: Decimal
    notes: str | None = None

    model_config = ConfigDict(from_attributes=True)
