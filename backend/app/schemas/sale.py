from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import Money, ReadSchema

# The three named price levels a cashier can pick at checkout.
PriceLevel = Literal["detail", "gros", "super_gros"]


class SaleItemBase(BaseModel):
    quantity: int = Field(ge=1)
    price_level: PriceLevel = "detail"
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
    packaging_id: UUID | None = None
    packaging_label: str | None = None
    unit_count: int = 1


class PaymentRead(ReadSchema):
    sale_id: UUID
    amount: Money


class PaymentCreate(BaseModel):
    """Body of POST /sales/{id}/payments — a later payment on a credit sale."""

    amount: Money = Field(gt=0)


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
    customer_id: UUID | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    guest_confirmed_at: datetime | None = None
    paid_amount: Money
    balance: Money
    items: list[SaleItemRead]
    payments: list[PaymentRead] = []


class AssignCustomerRequest(BaseModel):
    """Body of POST /sales/{id}/customer — attach a client to a null-customer
    sale. Confirm-guest needs no body."""

    customer_id: UUID


class CartItem(BaseModel):
    """One checkout line as the cashier builds it.

    The client picks a price_level; the SERVER resolves the actual unit
    price from the product — the client never sends prices.
    unit_price_override is the manual-override path: when present it
    replaces the resolved price but is still subject to the price floor
    (price_super_gros) — rejected below it, never clamped.
    """

    product_id: UUID
    quantity: int = Field(ge=1)
    price_level: PriceLevel = "detail"
    unit_price_override: Money | None = None
    # When set, the server resolves the price from THIS packaging's price
    # level, applies THAT packaging's super_gros as the floor, and decrements
    # stock by quantity * packaging.unit_count. None -> current behavior.
    packaging_id: UUID | None = None


class PaymentInfo(BaseModel):
    """How the sale is paid at checkout.

    full     — paid in full; amount_paid is ignored (it IS the total).
    partial  — credit sale; amount_paid (0 <= amount < total) and a
               customer_id are REQUIRED (enforced in the service).
    """

    mode: Literal["full", "partial"] = "full"
    amount_paid: Money | None = None
    customer_id: UUID | None = None


class CheckoutRequest(BaseModel):
    store_id: UUID
    items: list[CartItem] = Field(min_length=1)
    payment: PaymentInfo = PaymentInfo()


class OutstandingSale(BaseModel):
    """One credit sale with money still owed — for lists and alerts."""

    model_config = ConfigDict(from_attributes=True)

    sale_id: UUID
    created_at: datetime
    customer_id: UUID | None
    customer_name: str | None
    customer_phone: str | None
    total_amount: Money
    paid_amount: Money
    balance: Money
    age_days: int
