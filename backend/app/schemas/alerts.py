from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.schemas.common import Money
from app.schemas.sale import OutstandingSale


class LowStockProduct(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    product_id: UUID
    name: str
    barcode: str | None
    stock_quantity: int
    low_stock_threshold: int


class AlertsSummary(BaseModel):
    """Badge counters for the notifications screen."""

    low_stock_count: int
    outstanding_credits_count: int
    outstanding_total: Money


class AlertsResponse(BaseModel):
    summary: AlertsSummary
    low_stock: list[LowStockProduct]
    # Sorted oldest debt first — the merchant chases the oldest money.
    outstanding_credits: list[OutstandingSale]
