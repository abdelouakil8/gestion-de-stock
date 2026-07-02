import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, StoreScopedMixin
from app.db.types import Money

if TYPE_CHECKING:
    from app.models.product import Product


class PriceTier(BaseModel, StoreScopedMixin):
    """Quantity-based price: applies from min_quantity units upward.

    A product has many tiers, read in ascending min_quantity order.
    Tier consistency rules (no duplicate thresholds, unit_price never below
    the product's min_sale_price) are enforced by the Phase 2 pricing service.
    """

    __tablename__ = "price_tiers"

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    min_quantity: Mapped[int] = mapped_column(nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Money, nullable=False)

    product: Mapped["Product"] = relationship(back_populates="price_tiers")
