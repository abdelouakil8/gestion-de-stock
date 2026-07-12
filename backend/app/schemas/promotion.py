"""Pydantic schemas for promotion codes."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field

from app.models.promotion import PromotionType
from app.schemas.common import Money, ReadSchema


class PromotionBase(BaseModel):
    code: str = Field(min_length=1, max_length=40)
    type: PromotionType
    value: Money = Field(gt=0)
    valid_from: datetime
    valid_to: datetime
    max_uses: int | None = Field(default=None, ge=1)


class PromotionCreate(PromotionBase):
    store_id: UUID


class PromotionRead(ReadSchema, PromotionBase):
    store_id: UUID
    used_count: int
    is_active: bool


class PromotionValidateRequest(BaseModel):
    store_id: UUID
    code: str = Field(min_length=1, max_length=40)
    subtotal: Money = Field(default=Decimal("0.00"))


class PromotionValidateResponse(BaseModel):
    valid: bool
    code: str
    type: PromotionType | None = None
    value: Money | None = None
    discount: Money = Decimal("0.00")
