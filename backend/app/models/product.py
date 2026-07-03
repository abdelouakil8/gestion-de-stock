import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, StoreScopedMixin
from app.db.types import Money

if TYPE_CHECKING:
    from app.models.category import Category


class Product(BaseModel, StoreScopedMixin):
    __tablename__ = "products"
    # DB-level backstops: no code path may ever drive stock negative, and the
    # three named price levels always keep their order (détail >= gros >=
    # super gros). Both rules are enforced first in the service layer.
    __table_args__ = (
        CheckConstraint("stock_quantity >= 0", name="stock_quantity_non_negative"),
        CheckConstraint(
            "price_detail >= price_gros AND price_gros >= price_super_gros",
            name="price_levels_ordered",
        ),
    )

    category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("categories.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # SKU / EAN — keyboard-wedge barcode scanners type this string at checkout.
    barcode: Mapped[str | None] = mapped_column(String(64), index=True)
    cost_price: Mapped[Decimal] = mapped_column(Money, nullable=False)
    # Named sale prices (Phase 6 — supersedes quantity-tier resolution).
    # price_super_gros doubles as the merchant's absolute floor: no sale
    # line may ever be finalized below it, from any path.
    price_detail: Mapped[Decimal] = mapped_column(Money, nullable=False)
    price_gros: Mapped[Decimal] = mapped_column(Money, nullable=False)
    price_super_gros: Mapped[Decimal] = mapped_column(Money, nullable=False)
    stock_quantity: Mapped[int] = mapped_column(nullable=False, default=0)
    # Alert threshold: the /alerts endpoint flags stock_quantity <= threshold.
    low_stock_threshold: Mapped[int] = mapped_column(nullable=False, default=5)
    # Relative path (under RUNTIME_DIR) of the optional product image;
    # the filename derives ONLY from the product UUID, never from uploads.
    image_path: Mapped[str | None] = mapped_column(String(255), default=None)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    category: Mapped["Category | None"] = relationship(back_populates="products")
