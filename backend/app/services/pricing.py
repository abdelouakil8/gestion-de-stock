"""Pricing rules — pure, deterministic, no database access.

Phase 6: named price levels (détail / gros / super gros) supersede
quantity-tier resolution. price_super_gros doubles as the merchant's
absolute floor. The floor is enforced HERE (and re-checked by every caller
that finalizes a sale line); it is never the UI's job and a violation is
always rejected, never clamped.
"""

from decimal import Decimal

from app.core.exceptions import (
    InvalidPriceLevelsError,
    InvalidQuantityError,
    PriceBelowFloorError,
)
from app.models import Product, ProductPackaging

_TWO_PLACES = Decimal("0.01")

# Price level -> column carrying that level's unit price. Both Product and
# ProductPackaging expose the same triplet (price_detail/gros/super_gros), so
# the same mapping drives base-unit and packaging price resolution.
PRICE_LEVEL_FIELDS = {
    "detail": "price_detail",
    "gros": "price_gros",
    "super_gros": "price_super_gros",
}


def validate_price_levels(
    price_detail: Decimal, price_gros: Decimal, price_super_gros: Decimal
) -> None:
    """Enforce détail >= gros >= super gros — rejected, never reordered."""
    if not (price_detail >= price_gros >= price_super_gros):
        raise InvalidPriceLevelsError(price_detail, price_gros, price_super_gros)


def resolve_unit_price(
    product: Product, price_level: str = "detail", quantity: int = 1
) -> Decimal:
    """Server-side price resolution: the chosen named level, from the
    product itself — the client never sends prices."""
    if quantity < 1:
        raise InvalidQuantityError(quantity)
    field = PRICE_LEVEL_FIELDS.get(price_level)
    if field is None:
        # Unreachable through the API (Pydantic Literal), kept as a guard
        # for direct service callers.
        raise InvalidPriceLevelsError(
            product.price_detail, product.price_gros, product.price_super_gros
        )
    return getattr(product, field)


def resolve_packaging_price(
    packaging: ProductPackaging, price_level: str = "detail"
) -> Decimal:
    """Server-side price resolution for a priced packaging (carton): the
    chosen named level from the packaging's OWN price triplet. The per-package
    price the cashier is charged — quantity multiplies it into the line total,
    unit_count only affects stock/cost, never revenue."""
    field = PRICE_LEVEL_FIELDS.get(price_level)
    if field is None:
        # Unreachable through the API (Pydantic Literal), kept as a guard
        # for direct service callers.
        raise InvalidPriceLevelsError(
            packaging.price_detail,
            packaging.price_gros,
            packaging.price_super_gros,
        )
    return getattr(packaging, field)


def validate_price_floor(
    product: Product, unit_price: Decimal, floor: Decimal | None = None
) -> None:
    """Reject (never clamp) any unit price below the floor (super gros).

    floor defaults to the product's own super gros; pass a packaging's
    price_super_gros to floor-check a per-package price against THAT
    packaging's minimum. product is still used for the error's product name.
    """
    effective_floor = product.price_super_gros if floor is None else floor
    if unit_price < effective_floor:
        raise PriceBelowFloorError(
            product_name=product.name,
            floor=effective_floor,
            attempted=unit_price,
        )


def line_total(unit_price: Decimal, quantity: int) -> Decimal:
    """Exact line total, normalized to 2 decimal places."""
    return (unit_price * quantity).quantize(_TWO_PLACES)
