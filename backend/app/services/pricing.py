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
from app.models import Product

_TWO_PLACES = Decimal("0.01")

# Price level -> Product column carrying that level's unit price.
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


def validate_price_floor(product: Product, unit_price: Decimal) -> None:
    """Reject (never clamp) any unit price below the floor (super gros)."""
    if unit_price < product.price_super_gros:
        raise PriceBelowFloorError(
            product_name=product.name,
            floor=product.price_super_gros,
            attempted=unit_price,
        )


def line_total(unit_price: Decimal, quantity: int) -> Decimal:
    """Exact line total, normalized to 2 decimal places."""
    return (unit_price * quantity).quantize(_TWO_PLACES)
