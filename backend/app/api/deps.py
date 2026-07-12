"""Request dependencies — DB session + role-aware authentication.

Auth model (Phase 17): named users with roles cashier < manager < owner. A PIN
login issues a session token (see app.core.sessions) sent on every request as
``X-Session-Token``. Three dependencies gate routes by a role floor and fail
CLOSED:

    require_cashier  — any authenticated user
    require_manager  — owner OR manager
    require_owner     — owner only

Backward compatibility (so existing installs and the whole test suite keep
working while the role system is adopted):
  * the legacy single owner PIN (settings.pin_hash / ``X-Owner-Pin``) is still
    accepted and resolves to an owner — this is the migration bridge;
  * until at least one named user exists, ``require_cashier`` stays permissive
    (checkout was public before this phase), so the app behaves exactly as it
    did under the single-PIN model. Manager/owner routes never fall open.
"""

from collections.abc import Generator
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import sessions
from app.core.config import settings
from app.core.security import verify_pin
from app.db.session import SessionLocal
from app.models.user import User, UserRole, role_at_least


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency providing one database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


DbDep = Annotated[Session, Depends(get_db)]

_SessionTokenHeader = Annotated[str | None, Header(alias="X-Session-Token")]
_OwnerPinHeader = Annotated[str | None, Header(alias="X-Owner-Pin")]


@dataclass(frozen=True)
class AuthUser:
    """The authenticated principal for a request.

    user_id/store_id are None for the legacy owner-PIN bridge (no User row)."""

    user_id: object | None
    name: str
    role: str
    store_id: object | None


def _resolve_auth(
    x_session_token: str | None, x_owner_pin: str | None
) -> AuthUser | None:
    """Resolve the principal from a session token or the legacy owner PIN."""
    session = sessions.get(x_session_token)
    if session is not None:
        return AuthUser(
            user_id=session.user_id,
            name=session.name,
            role=session.role,
            store_id=session.store_id,
        )
    if (
        x_owner_pin
        and settings.pin_hash is not None
        and verify_pin(x_owner_pin, settings.pin_hash)
    ):
        return AuthUser(
            user_id=None, name="Propriétaire", role=UserRole.owner.value, store_id=None
        )
    return None


def _has_active_users(db: Session) -> bool:
    return bool(
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.is_active.is_(True), User.deleted_at.is_(None))
        )
    )


def _raise_unauthenticated(db: Session) -> None:
    """Fail closed with the closest matching status.

    Preserves the pre-Phase-17 contract: a wholly unconfigured system (no PIN,
    no users) reports 409 pin_not_configured; otherwise 401."""
    if settings.pin_hash is None and not _has_active_users(db):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "pin_not_configured",
                "message": (
                    "Aucun code PIN n'est configuré. "
                    "Exécutez scripts/set_pin.py pour en définir un."
                ),
            },
        )
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": "invalid_pin", "message": "Authentification requise."},
    )


def _forbidden() -> None:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "forbidden",
            "message": "Votre rôle ne permet pas cette action.",
        },
    )


def require_cashier(
    db: DbDep,
    x_session_token: _SessionTokenHeader = None,
    x_owner_pin: _OwnerPinHeader = None,
) -> AuthUser:
    """Any authenticated user. Permissive until named users exist (open mode)."""
    user = _resolve_auth(x_session_token, x_owner_pin)
    if user is not None:
        return user
    # Open mode: no named users configured yet -> behave as the pre-role app
    # (checkout / payments were public). Once any user exists, this closes.
    if not _has_active_users(db):
        return AuthUser(
            user_id=None, name="Invité", role=UserRole.cashier.value, store_id=None
        )
    _raise_unauthenticated(db)


def require_manager(
    db: DbDep,
    x_session_token: _SessionTokenHeader = None,
    x_owner_pin: _OwnerPinHeader = None,
) -> AuthUser:
    """Owner or manager."""
    user = _resolve_auth(x_session_token, x_owner_pin)
    if user is None:
        _raise_unauthenticated(db)
    if not role_at_least(user.role, UserRole.manager):
        _forbidden()
    return user


def require_owner(
    db: DbDep,
    x_session_token: _SessionTokenHeader = None,
    x_owner_pin: _OwnerPinHeader = None,
) -> AuthUser:
    """Owner only."""
    user = _resolve_auth(x_session_token, x_owner_pin)
    if user is None:
        _raise_unauthenticated(db)
    if not role_at_least(user.role, UserRole.owner):
        _forbidden()
    return user


# Deprecated alias — kept so any lingering import resolves to the owner gate.
require_owner_pin = require_owner

# Dependency handles used in `dependencies=[...]` on the routers.
OwnerPinDep = Depends(require_owner)
OwnerDep = Depends(require_owner)
ManagerDep = Depends(require_manager)
CashierDep = Depends(require_cashier)

# Injectable variants (when a route needs the resolved AuthUser).
CurrentOwner = Annotated[AuthUser, Depends(require_owner)]
CurrentManager = Annotated[AuthUser, Depends(require_manager)]
CurrentUser = Annotated[AuthUser, Depends(require_cashier)]
