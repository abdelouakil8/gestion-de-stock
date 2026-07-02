"""CRUD for price tiers. Tier consistency rules land with Phase 2 pricing."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import PriceTier
from app.schemas.price_tier import PriceTierCreate


def create_price_tier(db: Session, data: PriceTierCreate) -> PriceTier:
    tier = PriceTier(**data.model_dump())
    db.add(tier)
    db.commit()
    db.refresh(tier)
    return tier


def get_price_tier(db: Session, tier_id: UUID) -> PriceTier | None:
    return db.scalar(
        select(PriceTier).where(
            PriceTier.id == tier_id, PriceTier.deleted_at.is_(None)
        )
    )


def list_price_tiers(db: Session, product_id: UUID) -> list[PriceTier]:
    """Tiers of one product, ascending by quantity threshold."""
    return list(
        db.scalars(
            select(PriceTier)
            .where(PriceTier.product_id == product_id, PriceTier.deleted_at.is_(None))
            .order_by(PriceTier.min_quantity)
        )
    )


def soft_delete_price_tier(db: Session, tier_id: UUID) -> PriceTier | None:
    tier = get_price_tier(db, tier_id)
    if tier is not None:
        tier.deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(tier)
    return tier
