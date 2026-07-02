from datetime import datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# Monetary amount: always Decimal (never float), non-negative, 2 decimals.
Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class ReadSchema(BaseModel):
    """Common fields of every *Read variant (mapped from ORM objects)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
