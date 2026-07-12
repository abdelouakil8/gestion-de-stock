"""Application users — the multi-role local auth model.

Replaces the single owner PIN with named users, each carrying a role
(cashier < manager < owner) and their own PBKDF2 PIN hash. The legacy single
PIN (settings.pin_hash / .env) is preserved as an owner-level fallback and is
migrated into an owner User on first login, so no existing install is ever
locked out.

Roles are ordered by privilege; the API dependencies (require_cashier /
require_manager / require_owner) fail closed, denying by default.
"""

from enum import StrEnum

from sqlalchemy import Enum as SAEnum
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel, StoreScopedMixin


class UserRole(StrEnum):
    cashier = "cashier"
    manager = "manager"
    owner = "owner"


# Privilege order — a user satisfies any role at or below their own.
_ROLE_RANK = {UserRole.cashier: 0, UserRole.manager: 1, UserRole.owner: 2}


def role_at_least(role: "UserRole | str", floor: "UserRole | str") -> bool:
    """True when `role` is privileged enough to satisfy `floor`."""
    try:
        return _ROLE_RANK[UserRole(role)] >= _ROLE_RANK[UserRole(floor)]
    except (KeyError, ValueError):
        return False


class User(BaseModel, StoreScopedMixin):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="userrole"), nullable=False, default=UserRole.cashier
    )
    # PBKDF2 hash (app.core.security.hash_pin) — never the plaintext PIN.
    pin_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<User id={self.id} name={self.name!r} role={self.role}>"
