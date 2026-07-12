"""Pydantic schemas for users and the login flow."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.models.user import UserRole
from app.schemas.common import ReadSchema


class UserBase(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    role: UserRole = UserRole.cashier


class UserCreate(UserBase):
    store_id: UUID
    pin: str = Field(min_length=4, max_length=64)


class UserUpdate(BaseModel):
    """Every field optional — only what is sent is changed."""

    name: str | None = Field(default=None, min_length=1, max_length=120)
    role: UserRole | None = None
    pin: str | None = Field(default=None, min_length=4, max_length=64)
    is_active: bool | None = None


class UserRead(ReadSchema, UserBase):
    """Never carries pin_hash."""

    store_id: UUID
    is_active: bool


class LoginUser(BaseModel):
    """Minimal, public user info for the login picker (no store/timestamps)."""

    id: UUID
    name: str
    role: UserRole


class LoginRequest(BaseModel):
    user_id: UUID
    pin: str = Field(min_length=1, max_length=64)


class LoginResponse(BaseModel):
    token: str
    user: LoginUser
