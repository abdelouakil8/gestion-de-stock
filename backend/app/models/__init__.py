"""SQLAlchemy models — no business logic in models, ever.

Every model module is imported here so that Alembic autogenerate and
Base.metadata.create_all() see the full metadata through a single import.

Phase 6: PriceTier was removed — named price levels live on Product now
(see the phase-6 migration docstring for the archival decision).
"""

from app.db.base import Base
from app.models.category import Category
from app.models.customer import Customer
from app.models.day_closing import DayClosing
from app.models.product import Product
from app.models.product_packaging import ProductPackaging
from app.models.promotion import Promotion, PromotionType
from app.models.purchase_order import (
    PurchaseOrder,
    PurchaseOrderItem,
    SupplierPayment,
)
from app.models.refund import Refund, RefundItem
from app.models.reservation import Reservation, ReservationItem, ReservationStatus
from app.models.sale import Payment, Sale, SaleItem
from app.models.sale_sequence import SaleSequence
from app.models.stock_movement import MovementType, StockMovement
from app.models.store import Store
from app.models.store_settings import StoreSettings
from app.models.supplier import Supplier
from app.models.user import User, UserRole

__all__ = [
    "Base",
    "Category",
    "Customer",
    "DayClosing",
    "Payment",
    "Product",
    "ProductPackaging",
    "Promotion",
    "PromotionType",
    "PurchaseOrder",
    "PurchaseOrderItem",
    "Refund",
    "RefundItem",
    "Reservation",
    "ReservationItem",
    "ReservationStatus",
    "Sale",
    "SaleItem",
    "SaleSequence",
    "StockMovement",
    "MovementType",
    "Store",
    "StoreSettings",
    "Supplier",
    "SupplierPayment",
    "User",
    "UserRole",
]
