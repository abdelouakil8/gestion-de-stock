from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel, StoreScopedMixin


class Supplier(BaseModel, StoreScopedMixin):
    """A goods supplier — mirrors Customer's structure exactly."""

    __tablename__ = "suppliers"
    __table_args__ = (
        Index(
            "uq_suppliers_store_phone_active",
            "store_id",
            "phone",
            unique=True,
            sqlite_where=text("deleted_at IS NULL"),
            postgresql_where=text("deleted_at IS NULL"),
        ),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), default=None)
    search_text: Mapped[str] = mapped_column(
        String(400), nullable=False, default="", server_default=""
    )
