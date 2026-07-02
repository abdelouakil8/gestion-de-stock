from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Money, ReadSchema


class PriceTierBase(BaseModel):
    min_quantity: int = Field(ge=1)
    unit_price: Money


class PriceTierCreate(PriceTierBase):
    store_id: UUID
    product_id: UUID


class PriceTierUpdate(BaseModel):
    min_quantity: int | None = Field(default=None, ge=1)
    unit_price: Money | None = None


class PriceTierRead(ReadSchema, PriceTierBase):
    store_id: UUID
    product_id: UUID
