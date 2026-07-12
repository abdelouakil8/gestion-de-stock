from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import DbDep
from app.core import sessions
from app.core.config import RUNTIME_DIR, settings
from app.core.security import hash_pin, verify_pin
from app.schemas.user import LoginRequest, LoginResponse, LoginUser
from app.services import users as users_service

router = APIRouter()


class PinVerifyRequest(BaseModel):
    pin: str = Field(min_length=0, max_length=64)


class PinSetRequest(BaseModel):
    pin: str = Field(min_length=1, max_length=64)


class PinVerifyResponse(BaseModel):
    valid: bool


@router.post("/verify", response_model=PinVerifyResponse)
def verify(payload: PinVerifyRequest) -> PinVerifyResponse:
    """App-open / sensitive-action gate. Returns 200 only for a correct PIN."""
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
    if not verify_pin(payload.pin, settings.pin_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_pin", "message": "Code PIN incorrect."},
        )
    return PinVerifyResponse(valid=True)


@router.get("/status")
def get_status() -> dict:
    """Check if the PIN is configured, without triggering auth failures."""
    return {"configured": settings.pin_hash is not None}


@router.get("/users", response_model=list[LoginUser])
def login_users(db: DbDep) -> list:
    """Public list of selectable users for the login screen (no PIN hashes).

    Lazily migrates the legacy single owner PIN into an owner User so an
    upgraded install always has at least the owner to pick."""
    return users_service.login_users(db)


@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest, db: DbDep) -> LoginResponse:
    """Authenticate a user by PIN and issue a session token."""
    user = users_service.authenticate(db, payload.user_id, payload.pin)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "invalid_pin", "message": "Code PIN incorrect."},
        )
    session = sessions.create(user)
    return LoginResponse(
        token=session.token,
        user=LoginUser(id=user.id, name=user.name, role=user.role),
    )


@router.post("/logout", status_code=204)
def logout(
    x_session_token: Annotated[str | None, Header(alias="X-Session-Token")] = None,
) -> None:
    """Revoke the current session token (best-effort)."""
    sessions.revoke(x_session_token)


@router.post("/set-pin", response_model=PinVerifyResponse)
def set_pin(payload: PinSetRequest) -> PinVerifyResponse:
    """One-time wizard setup to set the initial PIN."""
    if settings.pin_hash is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "pin_already_configured",
                "message": "Le code PIN est déjà configuré.",
            },
        )

    hashed = hash_pin(payload.pin)

    env_file = RUNTIME_DIR / ".env"
    lines = []
    if env_file.exists():
        lines = env_file.read_text("utf-8").splitlines()

    lines = [line for line in lines if not line.startswith("PIN_HASH=")]
    lines.append(f"PIN_HASH={hashed}")
    env_file.write_text("\n".join(lines) + "\n", "utf-8")

    settings.pin_hash = hashed
    return PinVerifyResponse(valid=True)
