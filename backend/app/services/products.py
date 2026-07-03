"""CRUD for products + the price-level ordering rule (Phase 6)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Product
from app.schemas.product import ProductCreate, ProductUpdate
from app.services import pricing


def create_product(db: Session, data: ProductCreate) -> Product:
    pricing.validate_price_levels(
        data.price_detail, data.price_gros, data.price_super_gros
    )
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


def get_product_by_barcode(db: Session, store_id: UUID, barcode: str) -> Product | None:
    """Barcode lookup for scanner-driven checkout (active products only)."""
    return db.scalar(
        select(Product).where(
            Product.store_id == store_id,
            Product.barcode == barcode,
            Product.deleted_at.is_(None),
            Product.is_active.is_(True),
        )
    )


def update_product(
    db: Session, product_id: UUID, data: ProductUpdate
) -> Product | None:
    product = get_product(db, product_id)
    if product is not None:
        changes = data.model_dump(exclude_unset=True)
        # Validate the RESULTING price levels (submitted values merged over
        # current ones) so a partial update can never break the ordering.
        pricing.validate_price_levels(
            changes.get("price_detail", product.price_detail),
            changes.get("price_gros", product.price_gros),
            changes.get("price_super_gros", product.price_super_gros),
        )
        for field, value in changes.items():
            setattr(product, field, value)
        db.commit()
        db.refresh(product)
    return product


def soft_delete_product(db: Session, product_id: UUID) -> Product | None:
    """Archive a product. The row is kept — sale history references it."""
    product = get_product(db, product_id)
    if product is not None:
        product.deleted_at = datetime.now(UTC)
        db.commit()
        db.refresh(product)
    return product
