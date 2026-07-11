from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ReadSchema

# A customer's preferred selling tier, mirrored from SaleItem.price_level.
PriceLevel = Literal["detail", "gros", "super_gros"]


class CustomerBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=1, max_length=32)
    note: str | None = Field(default=None, max_length=500)
    # Auto-applied at the caisse when attached; None = no preference.
    default_price_level: PriceLevel | None = None


class CustomerCreate(CustomerBase):
    store_id: UUID


class CustomerUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, min_length=1, max_length=32)
    note: str | None = Field(default=None, max_length=500)
    default_price_level: PriceLevel | None = None


class CustomerRead(ReadSchema, CustomerBase):
    store_id: UUID
