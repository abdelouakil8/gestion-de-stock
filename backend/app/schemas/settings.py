from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import ReadSchema

# Hex color like "#1A2B3C" — validated at the schema boundary.
_HEX_COLOR = r"^#[0-9a-fA-F]{6}$"


class SettingsBase(BaseModel):
    shop_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    address: str | None = Field(default=None, max_length=200)
    footer_message: str | None = Field(default=None, max_length=200)
    show_credit_details: bool = True
    ui_language: Literal["fr", "ar"] = "fr"
    theme_accent: str = Field(default="#2563EB", pattern=_HEX_COLOR)
    theme_mode: Literal["light", "dark"] = "light"
    theme_bg: str | None = Field(default=None, pattern=_HEX_COLOR)
    theme_surface: str | None = Field(default=None, pattern=_HEX_COLOR)
    theme_text: str | None = Field(default=None, pattern=_HEX_COLOR)
    theme_border: str | None = Field(default=None, pattern=_HEX_COLOR)


class SettingsUpdate(BaseModel):
    shop_name: str | None = Field(default=None, max_length=120)
    phone: str | None = Field(default=None, max_length=32)
    address: str | None = Field(default=None, max_length=200)
    footer_message: str | None = Field(default=None, max_length=200)
    show_credit_details: bool | None = None
    ui_language: Literal["fr", "ar"] | None = None
    theme_accent: str | None = Field(default=None, pattern=_HEX_COLOR)
    theme_mode: Literal["light", "dark"] | None = None
    theme_bg: str | None = Field(default=None, pattern=_HEX_COLOR)
    theme_surface: str | None = Field(default=None, pattern=_HEX_COLOR)
    theme_text: str | None = Field(default=None, pattern=_HEX_COLOR)
    theme_border: str | None = Field(default=None, pattern=_HEX_COLOR)


class SettingsRead(ReadSchema, SettingsBase):
    store_id: UUID
