"""Promotion codes — management (owner) + validation (cashier)."""

from uuid import UUID

from fastapi import APIRouter

from app.api.deps import CashierDep, DbDep, OwnerDep
from app.schemas.promotion import (
    PromotionCreate,
    PromotionRead,
    PromotionValidateRequest,
    PromotionValidateResponse,
)
from app.services import promotions

router = APIRouter()


@router.get("", response_model=list[PromotionRead], dependencies=[OwnerDep])
def list_promotions(store_id: UUID, db: DbDep, active_only: bool = False) -> list:
    """Every non-deleted promotion of the store (owner management view)."""
    return promotions.list_promotions(db, store_id, active_only=active_only)


@router.post("", response_model=PromotionRead, status_code=201, dependencies=[OwnerDep])
def create_promotion(payload: PromotionCreate, db: DbDep):
    return promotions.create_promotion(db, payload)


@router.post(
    "/validate",
    response_model=PromotionValidateResponse,
    dependencies=[CashierDep],
)
def validate_promotion(payload: PromotionValidateRequest, db: DbDep):
    """Preview a code's discount at the caisse (does not consume a use).

    Raises a structured error (409 promo_invalid) when the code is unknown,
    inactive, expired or exhausted."""
    promo, discount = promotions.validate(
        db, payload.store_id, payload.code, payload.subtotal
    )
    return PromotionValidateResponse(
        valid=True,
        code=promo.code,
        type=promo.type,
        value=promo.value,
        discount=discount,
    )


@router.delete("/{promo_id}", status_code=204, dependencies=[OwnerDep])
def deactivate_promotion(promo_id: UUID, db: DbDep) -> None:
    promotions.deactivate_promotion(db, promo_id)
