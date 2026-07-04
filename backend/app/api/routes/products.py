from uuid import UUID

from fastapi import APIRouter, Query, Response, UploadFile

from app.api.deps import DbDep, OwnerPinDep
from app.core.exceptions import NotFoundError
from app.schemas.product import (
    ProductCreate,
    ProductRead,
    ProductReadWithCost,
    ProductUpdate,
)
from app.services import images, products

router = APIRouter()

# Cashier-facing endpoints return ProductRead (never cost_price).
# Owner endpoints (PIN-gated) return ProductReadWithCost.


@router.get("", response_model=list[ProductRead])
def list_products(
    store_id: UUID,
    db: DbDep,
    q: str | None = Query(default=None, max_length=200),
    limit: int | None = Query(default=None, ge=1, le=200),
    active_only: bool = Query(default=False),
) -> list:
    """Store products; q runs the smart search, limit caps results.

    With no filters the full store catalog is returned (frontend prefetch)."""
    return products.list_products(
        db, store_id, query=q, limit=limit, active_only=active_only
    )


@router.get("/by-barcode/{barcode}", response_model=ProductRead)
def get_by_barcode(store_id: UUID, barcode: str, db: DbDep):
    product = products.get_product_by_barcode(db, store_id, barcode)
    if product is None:
        raise NotFoundError("produit", barcode)
    return product


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: UUID, db: DbDep):
    product = products.get_product(db, product_id)
    if product is None:
        raise NotFoundError("produit", product_id)
    return product


@router.get(
    "/{product_id}/details",
    response_model=ProductReadWithCost,
    dependencies=[OwnerPinDep],
)
def get_product_details(product_id: UUID, db: DbDep):
    product = products.get_product(db, product_id)
    if product is None:
        raise NotFoundError("produit", product_id)
    return product


@router.post(
    "", response_model=ProductReadWithCost, status_code=201, dependencies=[OwnerPinDep]
)
def create_product(payload: ProductCreate, db: DbDep):
    return products.create_product(db, payload)


@router.patch(
    "/{product_id}", response_model=ProductReadWithCost, dependencies=[OwnerPinDep]
)
def update_product(product_id: UUID, payload: ProductUpdate, db: DbDep):
    product = products.update_product(db, product_id, payload)
    if product is None:
        raise NotFoundError("produit", product_id)
    return product


@router.delete("/{product_id}", status_code=204, dependencies=[OwnerPinDep])
def archive_product(product_id: UUID, db: DbDep) -> None:
    if products.soft_delete_product(db, product_id) is None:
        raise NotFoundError("produit", product_id)


# ------------------------------------------------------------- image


@router.post(
    "/{product_id}/image",
    response_model=ProductReadWithCost,
    status_code=201,
    dependencies=[OwnerPinDep],
)
def upload_product_image(product_id: UUID, file: UploadFile, db: DbDep):
    """Attach or replace the product image (JPEG/PNG/WebP, ≤ 2 Mo).

    The stored filename derives only from the product UUID — the uploaded
    filename is never trusted."""
    product = products.get_product(db, product_id)
    if product is None:
        raise NotFoundError("produit", product_id)
    data = file.file.read()
    return images.save_product_image(db, product, data, file.content_type)


@router.get("/{product_id}/image")
def get_product_image(product_id: UUID, db: DbDep) -> Response:
    product = products.get_product(db, product_id)
    if product is None:
        raise NotFoundError("produit", product_id)
    path = images.image_file_path(product)
    if path is None or not path.is_file():
        raise NotFoundError("image", product_id)
    return Response(
        content=path.read_bytes(), media_type=images.image_media_type(product)
    )


@router.delete("/{product_id}/image", status_code=204, dependencies=[OwnerPinDep])
def delete_product_image(product_id: UUID, db: DbDep) -> None:
    product = products.get_product(db, product_id)
    if product is None:
        raise NotFoundError("produit", product_id)
    images.delete_product_image(db, product)
