from sqlalchemy import Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel, StoreScopedMixin


class Customer(BaseModel, StoreScopedMixin):
    """A known buyer — required for credit sales, optional otherwise."""

    __tablename__ = "customers"
    # Phone unique per store among non-deleted rows (partial-index backstop,
    # works on both SQLite and PostgreSQL; the service layer enforces the
    # rule first with a French error message).
    __table_args__ = (
        Index(
            "uq_customers_store_phone_active",
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
    # Preferred price level applied automatically at the caisse when this
    # customer is attached ("detail" | "gros" | "super_gros"). NULL = no
    # preference (the cashier keeps whatever level each line already has).
    default_price_level: Mapped[str | None] = mapped_column(String(16), default=None)
    # Precomputed normalized text: NFKC + casefold + accent/tashkeel folding,
    # used by smart search.
    search_text: Mapped[str] = mapped_column(
        String(400), nullable=False, default="", server_default=""
    )
