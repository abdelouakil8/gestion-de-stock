from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Money, ReadSchema


class ProductBase(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    barcode: str | None = Field(default=None, max_length=64)
    category_id: UUID | None = None
    # Named sale prices — the ordering rule (détail >= gros >= super gros)
    # is enforced in the service layer, where cross-field context lives.
    price_detail: Money
    price_gros: Money
    price_super_gros: Money
    stock_quantity: int = Field(default=0, ge=0)
    low_stock_threshold: int = Field(default=5, ge=0)
    is_active: bool = True


class ProductCreate(ProductBase):
    """Owner action — carries cost_price (required, never optional)."""

    store_id: UUID
    cost_price: Money


class ProductUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    barcode: str | None = Field(default=None, max_length=64)
    category_id: UUID | None = None
    cost_price: Money | None = None
    price_detail: Money | None = None
    price_gros: Money | None = None
    price_super_gros: Money | None = None
    stock_quantity: int | None = Field(default=None, ge=0)
    low_stock_threshold: int | None = Field(default=None, ge=0)
    is_active: bool | None = None


class ProductRead(ReadSchema, ProductBase):
    """Cashier-safe view — cost_price is NEVER included here.

    Any endpoint a cashier-facing screen consumes must return this schema.
    """

    store_id: UUID
    image_path: str | None = None


class ProductReadWithCost(ProductRead):
    """Owner/reporting view ONLY — the sole schema exposing cost_price."""

    cost_price: Money
