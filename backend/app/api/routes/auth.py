from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.security import verify_pin

router = APIRouter()


class PinVerifyRequest(BaseModel):
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
