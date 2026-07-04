import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, StoreScopedMixin
from app.db.types import Money

if TYPE_CHECKING:
    from app.models.product import Product


class ProductPackaging(BaseModel, StoreScopedMixin):
    """A PRICED packaging (e.g. a carton) — an additional sale unit of the
    SAME product with its own price triplet.

    unit_count is the number of base stock units one package consumes; the
    line's base_units = quantity * unit_count. The product's implicit base
    unit (unit_count=1, prices on Product) is NOT a row here.
    """

    __tablename__ = "product_packagings"
    # DB-level backstops for the two service-layer rules: a package always
    # consumes at least one base unit, and its three named price levels keep
    # their order (détail >= gros >= super gros). Enforced first in the
    # service layer (InvalidPriceLevelsError / PriceBelowFloorError).
    __table_args__ = (
        CheckConstraint("unit_count >= 1", name="packaging_unit_count_positive"),
        CheckConstraint(
            "price_detail >= price_gros AND price_gros >= price_super_gros",
            name="packaging_price_levels_ordered",
        ),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("products.id"), nullable=False, index=True
    )
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    # Base stock units consumed per package (e.g. a carton of 12 -> 12).
    unit_count: Mapped[int] = mapped_column(nullable=False)
    # Package price levels; price_super_gros doubles as this packaging's
    # absolute floor, exactly as on Product.
    price_detail: Mapped[Decimal] = mapped_column(Money, nullable=False)
    price_gros: Mapped[Decimal] = mapped_column(Money, nullable=False)
    price_super_gros: Mapped[Decimal] = mapped_column(Money, nullable=False)
    # Display order in the packaging picker.
    position: Mapped[int] = mapped_column(nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    product: Mapped["Product"] = relationship()
