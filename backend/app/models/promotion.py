"""Promotion codes (coupons) — store-scoped, time-boxed, use-capped.

A code carries either a percentage or a fixed amount off the cart total. The
``used_count`` is incremented atomically at checkout (a single conditional
UPDATE), so a code capped at ``max_uses`` can never be over-redeemed under
concurrent sales. Codes are soft-deleted (deactivated), never hard-removed.
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel, StoreScopedMixin
from app.db.types import Money


class PromotionType(StrEnum):
    percent = "percent"
    fixed = "fixed"


class Promotion(BaseModel, StoreScopedMixin):
    __tablename__ = "promotions"

    # Stored uppercase, matched case-insensitively at validation time.
    code: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    type: Mapped[PromotionType] = mapped_column(
        SAEnum(PromotionType, name="promotiontype"), nullable=False
    )
    # percent: 0-100 (a percentage); fixed: a flat amount off the total.
    value: Mapped[Decimal] = mapped_column(Money, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    valid_to: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # NULL = unlimited uses.
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True, default=None)
    used_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<Promotion code={self.code!r} type={self.type} value={self.value}>"
