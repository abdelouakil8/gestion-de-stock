"""Pydantic schemas for stock movement ledger responses."""

from uuid import UUID

from pydantic import BaseModel

from app.models.stock_movement import MovementType
from app.schemas.common import ReadSchema


class StockMovementRead(ReadSchema):
    store_id: UUID
    product_id: UUID
    movement_type: MovementType
    quantity_delta: int
    quantity_after: int
    reference_id: UUID | None
    note: str | None


class StockMovementPage(BaseModel):
    items: list[StockMovementRead]
    total: int
