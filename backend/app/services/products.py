"""CRUD for products. No pricing logic here — that is the Phase 2 service."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product
from app.schemas.product import ProductCreate


def create_product(db: Session, data: ProductCreate) -> Product:
    product = Product(**data.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


def get_product(db: Session, product_id: UUID) -> Product | None:
    return db.scalar(
        select(Product).where(Product.id == product_id, Product.deleted_at.is_(None))
    )


def list_products(db: Session, store_id: UUID) -> list[Product]:
    return list(
        db.scalars(
            select(Product)
            .where(Product.store_id == store_id, Product.deleted_at.is_(None))
            .order_by(Product.name)
        )
    )


def soft_delete_product(db: Session, product_id: UUID) -> Product | None:
    """Archive a product. The row is kept — sale history references it."""
    product = get_product(db, product_id)
    if product is not None:
        product.deleted_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(product)
    return product
