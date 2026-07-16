from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Money, ReadSchema


class PackagingBase(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    # Base stock units consumed per package (>= 1).
    unit_count: int = Field(ge=1)
    # Ordering rule (détail >= gros >= super gros) enforced in the service.
    price_detail: Money
    price_gros: Money
    price_super_gros: Money
    position: int = 0
    is_active: bool = True


class PackagingCreate(PackagingBase):
    """Nested under a product create/update — no product_id here."""


class PackagingRead(ReadSchema, PackagingBase):
    product_id: UUID
    store_id: UUID


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
    # Priced packagings created alongside the product. None or [] both start
    # a product with no packagings.
    packagings: list[PackagingCreate] | None = None


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
    # None = leave packagings unchanged; [] = clear all; a list = replace.
    packagings: list[PackagingCreate] | None = None


class ProductRead(ReadSchema, ProductBase):
    """Cashier-safe view — cost_price is NEVER included here.

    Any endpoint a cashier-facing screen consumes must return this schema.
    """

    store_id: UUID
    image_path: str | None = None
    # Units held by active layaway reservations (available = stock - reserved).
    reserved_quantity: int = 0
    packagings: list[PackagingRead] = []


class ProductReadWithCost(ProductRead):
    """Owner/reporting view ONLY — the sole schema exposing cost_price."""

    cost_price: Money


class ProductPage(BaseModel):
    items: list[ProductRead]
    total: int
