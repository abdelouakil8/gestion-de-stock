"""Pydantic schemas for stock movement ledger responses."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.stock_movement import MovementType
from app.schemas.common import ReadSchema


class StockMovementRead(ReadSchema):
    store_id: UUID
    product_id: UUID
    movement_type: MovementType
    quantity_delta: int
    quantity_after: int
    reference_id: UUID | None
    reason: str | None = None
    note: str | None


class StockMovementPage(BaseModel):
    items: list[StockMovementRead]
    total: int


class StockAdjustRequest(BaseModel):
    """Body of POST /products/{id}/adjust-stock — set the counted real stock.

    new_quantity is the absolute counted quantity (never a delta); the server
    computes delta = new_quantity - current_stock and writes an ``adjustment``
    movement. reason is a short motive code; note is an optional free comment.
    """

    new_quantity: int = Field(ge=0, le=99_999)
    reason: str = Field(min_length=1, max_length=32)
    note: str | None = Field(default=None, max_length=500)


class GlobalMovementRead(BaseModel):
    """One ledger entry enriched with the product name / barcode / category,
    joined server-side so the movements screen never does N+1 lookups."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    store_id: UUID
    product_id: UUID
    product_name: str
    product_barcode: str | None = None
    category_name: str | None = None
    movement_type: MovementType
    quantity_delta: int
    quantity_after: int
    reference_id: UUID | None = None
    reason: str | None = None
    note: str | None = None


class GlobalMovementPage(BaseModel):
    items: list[GlobalMovementRead]
    total: int
