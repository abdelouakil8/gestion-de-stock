"""Pydantic v2 schemas for API request/response validation.

Monetary amounts always use decimal.Decimal (see schemas.common.Money) —
never float. cost_price only ever appears in owner/reporting schemas
(ProductCreate, ProductUpdate, ProductReadWithCost), never in cashier-facing
ones (ProductRead, sale schemas).
"""

from app.schemas.category import CategoryCreate, CategoryRead, CategoryUpdate
from app.schemas.common import Money, ReadSchema
from app.schemas.price_tier import PriceTierCreate, PriceTierRead, PriceTierUpdate
from app.schemas.product import (
    ProductCreate,
    ProductRead,
    ProductReadWithCost,
    ProductUpdate,
)
from app.schemas.sale import (
    SaleCreate,
    SaleItemCreate,
    SaleItemRead,
    SaleItemUpdate,
    SaleRead,
    SaleUpdate,
)
from app.schemas.store import StoreCreate, StoreRead, StoreUpdate

__all__ = [
    "CategoryCreate",
    "CategoryRead",
    "CategoryUpdate",
    "Money",
    "PriceTierCreate",
    "PriceTierRead",
    "PriceTierUpdate",
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
    "StoreCreate",
    "StoreRead",
    "StoreUpdate",
]
