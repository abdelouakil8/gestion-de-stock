import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class StoreSettings(BaseModel):
    """Per-store settings (1:1 with Store) — receipt fields and UI options.

    Value validation (language whitelist, hex color) lives in the schema /
    service layer; the model stays dumb.
    """

    __tablename__ = "store_settings"

    store_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("stores.id"), nullable=False, unique=True, index=True
    )
    # Receipt header/footer — shop_name overrides Store.name when set.
    shop_name: Mapped[str | None] = mapped_column(String(120), default=None)
    phone: Mapped[str | None] = mapped_column(String(32), default=None)
    address: Mapped[str | None] = mapped_column(String(200), default=None)
    footer_message: Mapped[str | None] = mapped_column(String(200), default=None)
    # When true and the sale is partially paid, the receipt prints the paid
    # amount and the remaining balance.
    show_credit_details: Mapped[bool] = mapped_column(nullable=False, default=True)
    ui_language: Mapped[str] = mapped_column(String(2), nullable=False, default="fr")
    theme_accent: Mapped[str] = mapped_column(
        String(7), nullable=False, default="#2563EB"
    )
    # Theme mode ("light" | "dark") + optional per-role custom overrides. A
    # NULL override means "use the mode default"; a hex string overrides that
    # structural color. Validation (mode whitelist, hex) lives in the schema.
    theme_mode: Mapped[str] = mapped_column(
        String(5), nullable=False, default="light", server_default="light"
    )
    theme_bg: Mapped[str | None] = mapped_column(String(7), default=None)
    theme_surface: Mapped[str | None] = mapped_column(String(7), default=None)
    theme_text: Mapped[str | None] = mapped_column(String(7), default=None)
    theme_border: Mapped[str | None] = mapped_column(String(7), default=None)
