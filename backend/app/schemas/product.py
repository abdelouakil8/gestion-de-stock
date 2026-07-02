from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Money, ReadSchema


class ProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    barcode: str | None = Field(default=None, max_length=64)
    category_id: UUID | None = None
    min_sale_price: Money
    stock_quantity: int = Field(default=0, ge=0)
    is_active: bool = True


class ProductCreate(ProductBase):
    """Owner action — carries cost_price."""

    store_id: UUID
    cost_price: Money


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    barcode: str | None = Field(default=None, max_length=64)
    category_id: UUID | None = None
    cost_price: Money | None = None
    min_sale_price: Money | None = None
    stock_quantity: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ProductRead(ReadSchema, ProductBase):
    """Cashier-safe view — cost_price is NEVER included here.

    Any endpoint a cashier-facing screen consumes must return this schema.
    """

    store_id: UUID


class ProductReadWithCost(ProductRead):
    """Owner/reporting view ONLY — the sole schema exposing cost_price."""

    cost_price: Money
