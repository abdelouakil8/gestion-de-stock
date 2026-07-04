import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, StoreScopedMixin
from app.db.types import Money

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.product_packaging import ProductPackaging


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
    # Precomputed normalized text: NFKC + casefold + accent/tashkeel folding,
    # used by smart search.
    search_text: Mapped[str] = mapped_column(
        String(400), nullable=False, default="", server_default=""
    )
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
    # Priced packagings (cartons) — additional sale units of THIS product,
    # each with its own price triplet. No delete-orphan cascade: packagings
    # are soft-deleted in the service layer, never removed by collection
    # edits. The primaryjoin hides soft-deleted rows so ProductRead only ever
    # serializes live packagings; the service queries active rows directly
    # when it needs to soft-delete the current set (see _sync_packagings).
    packagings: Mapped[list["ProductPackaging"]] = relationship(
        order_by="ProductPackaging.position",
        primaryjoin=(
            "and_(Product.id == ProductPackaging.product_id, "
            "ProductPackaging.deleted_at.is_(None))"
        ),
        viewonly=True,
    )
