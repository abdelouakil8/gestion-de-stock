"""Pydantic schemas for product reservations (layaway)."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.reservation import ReservationStatus
from app.schemas.common import Money
from app.schemas.sale import PaymentInfo, PriceLevel


class ReservationItemCreate(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1)
    price_level: PriceLevel = "detail"


class ReservationCreate(BaseModel):
    store_id: UUID
    customer_id: UUID
    expires_at: datetime
    deposit_amount: Money = Decimal("0.00")
    notes: str | None = Field(default=None, max_length=1000)
    items: list[ReservationItemCreate] = Field(min_length=1)


class ReservationItemRead(BaseModel):
    id: UUID
    product_id: UUID
    product_name: str
    quantity: int
    price_level: str
    unit_price_snapshot: Money
    line_total: Money


class ReservationRead(BaseModel):
    id: UUID
    store_id: UUID
    customer_id: UUID
    customer_name: str | None = None
    customer_phone: str | None = None
    created_at: datetime
    expires_at: datetime
    status: ReservationStatus
    deposit_amount: Money
    notes: str | None = None
    sale_id: UUID | None = None
    total_amount: Money
    is_expired: bool
    items: list[ReservationItemRead]


class ReservationComplete(BaseModel):
    """Body of POST /reservations/{id}/complete — how the final sale is paid."""

    payment: PaymentInfo = PaymentInfo()
