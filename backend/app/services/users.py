"""User management + login for the multi-role auth.

Business rules:
  * PINs are stored only as PBKDF2 hashes (app.core.security.hash_pin).
  * The pre-role single owner PIN (settings.pin_hash / .env) is migrated into
    an owner User the first time the login list is fetched, so no install is
    locked out. Conversely, creating/updating an owner's PIN keeps
    settings.pin_hash in sync so the legacy owner-PIN bridge and the
    re-confirmation dialogs stay valid within the running process.
  * The last active owner can never be demoted or deactivated — that would
    make owner-only administration unreachable.
"""

from uuid import UUID

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import RUNTIME_DIR, settings
from app.core.exceptions import AppError
from app.core.security import hash_pin, verify_pin
from app.models import Store, User
from app.models.user import UserRole
from app.schemas.user import UserCreate, UserUpdate


class UserNotFoundError(AppError):
    code = "user_not_found"

    def __init__(self, user_id: object) -> None:
        super().__init__("Utilisateur introuvable.", user_id=str(user_id))


class LastOwnerError(AppError):
    """Refuses to remove/demote the last owner — locks nobody out of admin."""

    code = "last_owner"

    def __init__(self) -> None:
        super().__init__("Impossible : au moins un propriétaire actif doit subsister.")


def _active_owner_count(db: Session, exclude_id: UUID | None = None) -> int:
    stmt = (
        select(func.count())
        .select_from(User)
        .where(
            User.role == UserRole.owner,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    if exclude_id is not None:
        stmt = stmt.where(User.id != exclude_id)
    return int(db.scalar(stmt) or 0)


def _persist_owner_pin(hashed: str) -> None:
    """Keep the legacy owner-PIN bridge (settings.pin_hash / .env) in sync with
    the current owner's PIN. Best-effort: a read-only .env never crashes admin."""
    settings.pin_hash = hashed
    try:
        env_file = RUNTIME_DIR / ".env"
        lines = env_file.read_text("utf-8").splitlines() if env_file.exists() else []
        lines = [line for line in lines if not line.startswith("PIN_HASH=")]
        lines.append(f"PIN_HASH={hashed}")
        env_file.write_text("\n".join(lines) + "\n", "utf-8")
    except OSError as exc:  # pragma: no cover - depends on filesystem perms
        logger.warning("Could not persist owner PIN to .env: {}", exc)


def list_users(db: Session, store_id: UUID) -> list[User]:
    """Every non-deleted user of the store (active and inactive), for admin."""
    return list(
        db.scalars(
            select(User)
            .where(User.store_id == store_id, User.deleted_at.is_(None))
            .order_by(User.role.desc(), User.name)
        )
    )


def login_users(db: Session) -> list[User]:
    """Active users for the login picker. Lazily migrates the legacy owner PIN
    into an owner User on first call so the picker is never empty on an
    upgraded install."""
    users = list(
        db.scalars(
            select(User)
            .where(User.is_active.is_(True), User.deleted_at.is_(None))
            .order_by(User.role.desc(), User.name)
        )
    )
    if users:
        return users
    if settings.pin_hash:
        store = db.scalar(select(Store).where(Store.deleted_at.is_(None)).limit(1))
        if store is not None:
            owner = User(
                store_id=store.id,
                name="Propriétaire",
                role=UserRole.owner,
                pin_hash=settings.pin_hash,
                is_active=True,
            )
            db.add(owner)
            db.commit()
            db.refresh(owner)
            logger.info("Bootstrapped owner user from the legacy PIN")
            return [owner]
    return []


def get_user(db: Session, user_id: UUID) -> User | None:
    return db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))


def create_user(db: Session, payload: UserCreate) -> User:
    user = User(
        store_id=payload.store_id,
        name=payload.name.strip(),
        role=payload.role,
        pin_hash=hash_pin(payload.pin),
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    if user.role == UserRole.owner:
        _persist_owner_pin(user.pin_hash)
    return user


def update_user(db: Session, user_id: UUID, payload: UserUpdate) -> User:
    user = get_user(db, user_id)
    if user is None:
        raise UserNotFoundError(user_id)

    was_owner = user.role == UserRole.owner
    # Guard the last active owner against demotion / deactivation.
    demoting = was_owner and payload.role is not None and payload.role != UserRole.owner
    deactivating = was_owner and payload.is_active is False and user.is_active
    if (demoting or deactivating) and _active_owner_count(db, exclude_id=user.id) == 0:
        raise LastOwnerError()

    if payload.name is not None:
        user.name = payload.name.strip()
    if payload.role is not None:
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active
    if payload.pin is not None:
        user.pin_hash = hash_pin(payload.pin)
    db.commit()
    db.refresh(user)
    # Keep the legacy bridge pointed at a current owner PIN.
    if user.role == UserRole.owner and user.is_active and payload.pin is not None:
        _persist_owner_pin(user.pin_hash)
    return user


def deactivate_user(db: Session, user_id: UUID) -> User:
    user = get_user(db, user_id)
    if user is None:
        raise UserNotFoundError(user_id)
    if (
        user.role == UserRole.owner
        and user.is_active
        and _active_owner_count(db, exclude_id=user.id) == 0
    ):
        raise LastOwnerError()
    user.is_active = False
    db.commit()
    db.refresh(user)
    return user


def authenticate(db: Session, user_id: UUID, pin: str) -> User | None:
    """Return the active user iff the PIN matches; None otherwise."""
    user = db.scalar(
        select(User).where(
            User.id == user_id,
            User.is_active.is_(True),
            User.deleted_at.is_(None),
        )
    )
    if user is None or not verify_pin(pin, user.pin_hash):
        return None
    return user
