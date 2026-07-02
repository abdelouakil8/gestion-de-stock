from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Money, ReadSchema


class SaleItemBase(BaseModel):
    quantity: int = Field(ge=1)
    unit_price_applied: Money
    line_total: Money


class SaleItemCreate(SaleItemBase):
    product_id: UUID


class SaleItemUpdate(BaseModel):
    """Sale items are immutable financial records — nothing is updatable.

    Kept for API symmetry; fields may appear later (e.g. a refund status).
    """


class SaleItemRead(ReadSchema, SaleItemBase):
    sale_id: UUID
    product_id: UUID


class SaleBase(BaseModel):
    total_amount: Money


class SaleCreate(SaleBase):
    store_id: UUID
    items: list[SaleItemCreate] = Field(min_length=1)


class SaleUpdate(BaseModel):
    """Sales are immutable financial records — nothing is updatable.

    Kept for API symmetry; fields may appear later (e.g. a status flag).
    """


class SaleRead(ReadSchema, SaleBase):
    store_id: UUID
    items: list[SaleItemRead]
