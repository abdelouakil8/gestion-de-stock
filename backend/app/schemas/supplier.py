from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Money, ReadSchema


class SupplierCreate(BaseModel):
    store_id: UUID
    name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=1, max_length=32)
    note: str | None = None


class SupplierUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    phone: str | None = Field(default=None, min_length=1, max_length=32)
    note: str | None = None


class SupplierRead(ReadSchema):
    store_id: UUID
    name: str
    phone: str
    note: str | None = None


class PurchaseOrderItemCreate(BaseModel):
    product_id: UUID
    quantity: int = Field(ge=1)
    unit_cost: Money


class PurchaseOrderCreate(BaseModel):
    store_id: UUID
    supplier_id: UUID
    items: list[PurchaseOrderItemCreate] = Field(min_length=1)
    payment_amount: Money | None = None
    payment_method: str = "cash"


class PurchaseOrderItemRead(ReadSchema):
    order_id: UUID
    product_id: UUID
    quantity: int
    unit_cost: Money
    line_total: Money


class PurchaseOrderRead(ReadSchema):
    store_id: UUID
    supplier_id: UUID
    total_amount: Money
    paid_amount: Money
    balance: Money
    status: str
    items: list[PurchaseOrderItemRead] = []


class SupplierPaymentCreate(BaseModel):
    amount: Money = Field(gt=0)
    payment_method: str = "cash"
