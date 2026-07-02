from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import BaseModel, StoreScopedMixin

if TYPE_CHECKING:
    from app.models.product import Product


class Category(BaseModel, StoreScopedMixin):
    __tablename__ = "categories"

    name: Mapped[str] = mapped_column(String(120), nullable=False)

    products: Mapped[list["Product"]] = relationship(back_populates="category")
