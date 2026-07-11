"""CRUD for products + the price-level ordering rule (Phase 6)."""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.textnorm import normalize_text
from app.models import Product, ProductPackaging
from app.models.stock_movement import MovementType
from app.schemas.product import PackagingCreate, ProductCreate, ProductUpdate
from app.services import inventory, pricing, search


def _product_search_text(name: str, barcode: str | None) -> str:
    """Canonical search string — mirrored in the migration backfill."""
    return normalize_text(f"{name} {barcode or ''}")


def _sync_packagings(
    db: Session, product: Product, packagings: list[PackagingCreate] | None
) -> None:
    """Replace the product's active packagings with the provided list.

    None -> leave existing packagings untouched (partial update). Otherwise
    every currently-active packaging is soft-deleted and the provided list is
    inserted with position = index. Each packaging's price ordering is
    validated first (same rule as the product), so a bad triplet aborts the
    whole write before any state changes."""
    if packagings is None:
        return
    for packaging in packagings:
        pricing.validate_price_levels(
            packaging.price_detail,
            packaging.price_gros,
            packaging.price_super_gros,
        )
    now = datetime.now(UTC)
    existing_active = db.scalars(
        select(ProductPackaging).where(
            ProductPackaging.product_id == product.id,
            ProductPackaging.deleted_at.is_(None),
        )
    ).all()
    for existing in existing_active:
        existing.deleted_at = now
    for index, packaging in enumerate(packagings):
        fields = packaging.model_dump()
        fields["position"] = index
        db.add(
            ProductPackaging(
                product_id=product.id,
                store_id=product.store_id,
                **fields,
            )
        )


def create_product(db: Session, data: ProductCreate) -> Product:
    pricing.validate_price_levels(
        data.price_detail, data.price_gros, data.price_super_gros
    )
    fields = data.model_dump(exclude={"packagings"})
    product = Product(**fields)
    product.search_text = _product_search_text(product.name, product.barcode)
    db.add(product)
    db.flush()  # assign product.id before inserting child packagings
    _sync_packagings(db, product, data.packagings)
    db.commit()
    return get_product(db, product.id)


def get_product(db: Session, product_id: UUID) -> Product | None:
    return db.scalar(
        select(Product)
        .options(selectinload(Product.packagings))
        .where(Product.id == product_id, Product.deleted_at.is_(None))
    )


def list_products(
    db: Session,
    store_id: UUID,
    *,
    query: str | None = None,
    limit: int | None = None,
    active_only: bool = False,
) -> list[Product]:
    """List store products.

    With no filters (query/limit/active_only all default) this returns EVERY
    non-deleted product of the store, ordered by name — the frontend catalog
    prefetch relies on the full, uncapped list. Any filter delegates to the
    smart search engine (LIKE prefilter + fuzzy fallback).
    """
    if query is None and limit is None and not active_only:
        return list(
            db.scalars(
                select(Product)
                .options(selectinload(Product.packagings))
                .where(Product.store_id == store_id, Product.deleted_at.is_(None))
                .order_by(Product.name)
            )
        )
    return search.search_products(
        db,
        store_id=store_id,
        query=query,
        limit=(limit or 20),
        active_only=active_only,
    )


def get_product_by_barcode(db: Session, store_id: UUID, barcode: str) -> Product | None:
    """Barcode lookup for scanner-driven checkout (active products only)."""
    return db.scalar(
        select(Product)
        .options(selectinload(Product.packagings))
        .where(
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
        # packagings is not a Product column — it is synced separately. None
        # (or absent) leaves the current set untouched; a list replaces it.
        changes.pop("packagings", None)
        # Validate the RESULTING price levels (submitted values merged over
        # current ones) so a partial update can never break the ordering.
        pricing.validate_price_levels(
            changes.get("price_detail", product.price_detail),
            changes.get("price_gros", product.price_gros),
            changes.get("price_super_gros", product.price_super_gros),
        )
        old_stock = product.stock_quantity
        for field, value in changes.items():
            setattr(product, field, value)
        # Recompute after all fields are merged, so name/barcode changes in
        # the same PATCH are reflected in a single canonical string.
        product.search_text = _product_search_text(product.name, product.barcode)
        _sync_packagings(db, product, data.packagings)
        # Record a ledger entry when stock was manually adjusted.
        if "stock_quantity" in changes:
            delta = product.stock_quantity - old_stock
            inventory.record_movement(
                db,
                store_id=product.store_id,
                product_id=product.id,
                delta=delta,
                after=product.stock_quantity,
                movement_type=MovementType.adjustment,
            )
        db.commit()
        product = get_product(db, product_id)
    return product


def soft_delete_product(db: Session, product_id: UUID) -> Product | None:
    """Archive a product. The row is kept — sale history references it."""
    product = get_product(db, product_id)
    if product is not None:
        product.deleted_at = datetime.now(UTC)
        db.commit()
        db.refresh(product)
    return product
