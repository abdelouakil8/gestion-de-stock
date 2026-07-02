"""CRUD for sales and their items.

Plain persistence only. Checkout logic — tier pricing, the minimum-price
floor, and the atomic stock decrement — is the Phase 2 checkout service;
nothing here validates prices or touches stock.
"""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Sale, SaleItem
from app.schemas.sale import SaleCreate


def create_sale(db: Session, data: SaleCreate) -> Sale:
    sale = Sale(
        store_id=data.store_id,
        total_amount=data.total_amount,
        items=[
            SaleItem(store_id=data.store_id, **item.model_dump())
            for item in data.items
        ],
    )
    db.add(sale)
    db.commit()
    db.refresh(sale)
    return sale


def get_sale(db: Session, sale_id: UUID) -> Sale | None:
    return db.scalar(
        select(Sale)
        .options(selectinload(Sale.items))
        .where(Sale.id == sale_id, Sale.deleted_at.is_(None))
    )


def list_sales(db: Session, store_id: UUID) -> list[Sale]:
    return list(
        db.scalars(
            select(Sale)
            .options(selectinload(Sale.items))
            .where(Sale.store_id == store_id, Sale.deleted_at.is_(None))
            .order_by(Sale.created_at.desc())
        )
    )


def soft_delete_sale(db: Session, sale_id: UUID) -> Sale | None:
    """Soft-delete a sale and its items together (never hard-deleted)."""
    sale = get_sale(db, sale_id)
    if sale is not None:
        now = datetime.now(timezone.utc)
        sale.deleted_at = now
        for item in sale.items:
            item.deleted_at = now
        db.commit()
        db.refresh(sale)
    return sale


def list_sale_items(db: Session, sale_id: UUID) -> list[SaleItem]:
    return list(
        db.scalars(
            select(SaleItem)
            .where(SaleItem.sale_id == sale_id, SaleItem.deleted_at.is_(None))
            .order_by(SaleItem.created_at)
        )
    )
