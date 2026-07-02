import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, StoreScopedMixin
from app.db.types import Money

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.price_tier import PriceTier


class Product(BaseModel, StoreScopedMixin):
    __tablename__ = "products"

    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # SKU / EAN — keyboard-wedge barcode scanners type this string at checkout.
    barcode: Mapped[str | None] = mapped_column(String(64), index=True)
    cost_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    # Absolute price floor set by the merchant. Enforcement happens in the
    # service layer at the moment of sale (Phase 2) — never in the UI alone.
    min_sale_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    stock_quantity: Mapped[int] = mapped_column(nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    category: Mapped["Category | None"] = relationship(back_populates="products")
    # No delete cascade — tiers are soft-deleted via the service layer only.
    price_tiers: Mapped[list["PriceTier"]] = relationship(
        back_populates="product",
        order_by="PriceTier.min_quantity",
    )
