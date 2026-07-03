from collections.abc import Generator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import verify_pin
from app.db.session import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency providing one database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_owner_pin(
    x_owner_pin: Annotated[str | None, Header(alias="X-Owner-Pin")] = None,
) -> None:
    """Guard for sensitive actions (price floor changes, product edits…).

    Auth abstraction point: routes only declare Depends(require_owner_pin);
    swapping this body for token-based auth later touches no route logic.
    """
    if settings.pin_hash is None:
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
    if x_owner_pin is None or not verify_pin(x_owner_pin, settings.pin_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_pin",
                "message": "Code PIN incorrect.",
            },
        )


DbDep = Annotated[Session, Depends(get_db)]
OwnerPinDep = Depends(require_owner_pin)
