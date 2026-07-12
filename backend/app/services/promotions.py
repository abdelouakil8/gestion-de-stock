"""Promotion codes — management + validation + atomic redemption.

validate() checks a code and computes the discount it would grant WITHOUT
consuming a use (for the "Appliquer" preview at the caisse). apply() is called
from within finalize_sale's transaction: it re-checks the code and increments
used_count with a single conditional UPDATE, so a capped code can never be
over-redeemed under concurrent checkouts (same pattern as the atomic stock
decrement / payment guard). Neither commits — the caller owns the transaction.
"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, PromotionInvalidError
from app.models.promotion import Promotion, PromotionType
from app.schemas.promotion import PromotionCreate


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None) if dt.tzinfo is not None else dt


def _find(db: Session, store_id: UUID, code: str) -> Promotion | None:
    return db.scalar(
        select(Promotion).where(
            Promotion.store_id == store_id,
            func.upper(Promotion.code) == code.strip().upper(),
            Promotion.is_active.is_(True),
            Promotion.deleted_at.is_(None),
        )
    )


def discount_for(promo: Promotion, subtotal: Decimal) -> Decimal:
    """The amount a code takes off `subtotal` (never more than the subtotal)."""
    if promo.type == PromotionType.percent:
        raw = subtotal * Decimal(promo.value) / Decimal(100)
    else:
        raw = Decimal(promo.value)
    return min(raw, subtotal).quantize(Decimal("0.01"))


def _check_window(promo: Promotion, now: datetime) -> None:
    if _naive(promo.valid_from) > now:
        raise PromotionInvalidError("Ce code promo n'est pas encore valide.")
    if _naive(promo.valid_to) < now:
        raise PromotionInvalidError("Ce code promo a expiré.")
    if promo.max_uses is not None and promo.used_count >= promo.max_uses:
        raise PromotionInvalidError("Ce code promo a atteint sa limite d'utilisation.")


def validate(
    db: Session,
    store_id: UUID,
    code: str,
    subtotal: Decimal,
    now: datetime | None = None,
) -> tuple[Promotion, Decimal]:
    """Check a code and compute its discount — does NOT consume a use."""
    promo = _find(db, store_id, code)
    if promo is None:
        raise PromotionInvalidError("Code promo invalide.")
    _check_window(promo, now or _now())
    return promo, discount_for(promo, subtotal)


def apply(
    db: Session,
    store_id: UUID,
    code: str,
    subtotal: Decimal,
    now: datetime | None = None,
) -> tuple[Promotion, Decimal]:
    """Redeem a code inside the caller's transaction (no commit).

    Re-checks validity, then atomically increments used_count guarded by
    max_uses so a capped code is never over-redeemed."""
    promo = _find(db, store_id, code)
    if promo is None:
        raise PromotionInvalidError("Code promo invalide.")
    _check_window(promo, now or _now())

    result = db.execute(
        update(Promotion)
        .where(
            Promotion.id == promo.id,
            Promotion.is_active.is_(True),
            or_(
                Promotion.max_uses.is_(None),
                Promotion.used_count < Promotion.max_uses,
            ),
        )
        .values(used_count=Promotion.used_count + 1)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise PromotionInvalidError("Ce code promo a atteint sa limite d'utilisation.")
    db.expire(promo, ["used_count"])
    return promo, discount_for(promo, subtotal)


# --------------------------------------------------------------- management


def list_promotions(db: Session, store_id: UUID, active_only: bool = False) -> list:
    stmt = select(Promotion).where(
        Promotion.store_id == store_id, Promotion.deleted_at.is_(None)
    )
    if active_only:
        stmt = stmt.where(Promotion.is_active.is_(True))
    return list(db.scalars(stmt.order_by(Promotion.created_at.desc())))


def create_promotion(db: Session, payload: PromotionCreate) -> Promotion:
    promo = Promotion(
        store_id=payload.store_id,
        code=payload.code.strip().upper(),
        type=payload.type,
        value=payload.value,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
        max_uses=payload.max_uses,
        used_count=0,
        is_active=True,
    )
    db.add(promo)
    db.commit()
    db.refresh(promo)
    return promo


def deactivate_promotion(db: Session, promo_id: UUID) -> Promotion:
    promo = db.scalar(
        select(Promotion).where(
            Promotion.id == promo_id, Promotion.deleted_at.is_(None)
        )
    )
    if promo is None:
        raise NotFoundError("promotion", promo_id)
    promo.is_active = False
    db.commit()
    db.refresh(promo)
    return promo
