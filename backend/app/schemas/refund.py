"""Refund (avoir) Pydantic schemas."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Money, ReadSchema


class RefundItemCreate(BaseModel):
    sale_item_id: UUID
    quantity: int = Field(ge=1)


class RefundCreate(BaseModel):
    items: list[RefundItemCreate] = Field(min_length=1)
    reason: str | None = None


class RefundItemRead(ReadSchema):
    refund_id: UUID
    sale_item_id: UUID
    quantity: int
    unit_count: int
    unit_price_refunded: Money
    line_total: Money


class RefundRead(ReadSchema):
    sale_id: UUID
    store_id: UUID
    reason: str | None
    total_amount: Money
    items: list[RefundItemRead]


class RefundableItem(BaseModel):
    sale_item_id: UUID
    product_id: UUID
    product_name: str
    packaging_label: str | None
    unit_count: int
    original_quantity: int
    already_refunded: int
    available: int
    unit_price: Money
