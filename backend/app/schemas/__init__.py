"""Pydantic v2 schemas for API request/response validation.

Monetary amounts always use decimal.Decimal (see schemas.common.Money) —
never float. cost_price only ever appears in owner/reporting schemas
(ProductCreate, ProductUpdate, ProductReadWithCost), never in cashier-facing
ones (ProductRead, sale schemas).
"""

from app.schemas.alerts import AlertsResponse, AlertsSummary, LowStockProduct
from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from app.schemas.common import Money, ReadSchema
from app.schemas.customer import CustomerCreate, CustomerRead, CustomerUpdate
from app.schemas.product import (
    ProductCreate,
    ProductRead,
    ProductReadWithCost,
    ProductUpdate,
)
from app.schemas.sale import (
    CartItem,
    CheckoutRequest,
    OutstandingSale,
    PaymentCreate,
    PaymentInfo,
    PaymentRead,
    SaleCreate,
    SaleItemCreate,
    SaleItemRead,
    SaleItemUpdate,
    SaleRead,
    SaleUpdate,
)
from app.schemas.settings import SettingsRead, SettingsUpdate
from app.schemas.store import StoreCreate, StoreRead, StoreUpdate

__all__ = [
    "AlertsResponse",
    "AlertsSummary",
    "CartItem",
    "CategoryCreate",
    "CategoryRead",
    "CategoryUpdate",
    "CheckoutRequest",
    "CustomerCreate",
    "CustomerRead",
    "CustomerUpdate",
    "LowStockProduct",
    "Money",
    "OutstandingSale",
    "PaymentCreate",
    "PaymentInfo",
    "PaymentRead",
    "ProductCreate",
    "ProductRead",
    "ProductReadWithCost",
    "ProductUpdate",
    "ReadSchema",
    "SaleCreate",
    "SaleItemCreate",
    "SaleItemRead",
    "SaleItemUpdate",
    "SaleRead",
    "SaleUpdate",
    "SettingsRead",
    "SettingsUpdate",
    "StoreCreate",
    "StoreRead",
    "StoreUpdate",
]
