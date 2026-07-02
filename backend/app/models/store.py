from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class Store(BaseModel):
    """Tenant root — every business row is scoped to a store."""

    __tablename__ = "stores"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
