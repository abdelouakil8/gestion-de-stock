from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query, Response, UploadFile

from app.api.deps import DbDep, ManagerDep
from app.core.exceptions import NotFoundError
from app.models.stock_movement import MovementType
from app.schemas.product import (
    LabelGenerateRequest,
    ProductCreate,
    ProductRead,
    ProductReadWithCost,
    ProductUpdate,
)
from app.schemas.stock_movement import (
    GlobalMovementPage,
    StockAdjustRequest,
    StockMovementPage,
)
from app.services import (
    images,
    import_export,
    inventory,
    labels,
    products,
    stock_movements,
)

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


# Registered BEFORE "/{product_id}": a literal path must win over the UUID
# path parameter, or FastAPI would try to coerce "movements" into a UUID.
@router.get("/movements", response_model=GlobalMovementPage, dependencies=[ManagerDep])
def list_all_movements(
    store_id: UUID,
    db: DbDep,
    product_id: UUID | None = None,
    category_id: UUID | None = None,
    type: MovementType | None = None,  # noqa: A002 (matches the query name)
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Store-wide movement ledger (owner), product name joined in, newest first."""
    items, total = stock_movements.list_all_movements(
        db,
        store_id=store_id,
        product_id=product_id,
        category_id=category_id,
        movement_type=type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total}


@router.post("/labels/generate", dependencies=[ManagerDep])
def generate_labels(
    store_id: UUID, payload: LabelGenerateRequest, db: DbDep
) -> Response:
    """Render the selected products as an A4 sheet of barcode labels (PDF)."""
    pdf = labels.build_labels_pdf(
        db, store_id, payload.product_ids, payload.label_config.model_dump()
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="etiquettes.pdf"'},
    )


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: UUID, db: DbDep):
    product = products.get_product(db, product_id)
    if product is None:
        raise NotFoundError("produit", product_id)
    return product


@router.post("/{product_id}/adjust-stock", dependencies=[ManagerDep])
def adjust_stock(product_id: UUID, payload: StockAdjustRequest, db: DbDep) -> dict:
    """Set a product's counted real stock (owner, PIN-gated).

    Writes an ``adjustment`` movement carrying the motive/note atomically and
    returns the before/after quantities so the UI can toast the change."""
    product, old_quantity, delta = inventory.adjust_stock(
        db,
        product_id,
        new_quantity=payload.new_quantity,
        reason=payload.reason,
        note=payload.note,
    )
    return {
        "product_id": str(product.id),
        "name": product.name,
        "old_quantity": old_quantity,
        "new_quantity": product.stock_quantity,
        "delta": delta,
    }


@router.get(
    "/{product_id}/details",
    response_model=ProductReadWithCost,
    dependencies=[ManagerDep],
)
def get_product_details(product_id: UUID, db: DbDep):
    product = products.get_product(db, product_id)
    if product is None:
        raise NotFoundError("produit", product_id)
    return product


@router.post(
    "", response_model=ProductReadWithCost, status_code=201, dependencies=[ManagerDep]
)
def create_product(payload: ProductCreate, db: DbDep):
    return products.create_product(db, payload)


@router.patch(
    "/{product_id}", response_model=ProductReadWithCost, dependencies=[ManagerDep]
)
def update_product(product_id: UUID, payload: ProductUpdate, db: DbDep):
    product = products.update_product(db, product_id, payload)
    if product is None:
        raise NotFoundError("produit", product_id)
    return product


@router.delete("/{product_id}", status_code=204, dependencies=[ManagerDep])
def archive_product(product_id: UUID, db: DbDep) -> None:
    if products.soft_delete_product(db, product_id) is None:
        raise NotFoundError("produit", product_id)


# ------------------------------------------------------------- image


@router.post(
    "/{product_id}/image",
    response_model=ProductReadWithCost,
    status_code=201,
    dependencies=[ManagerDep],
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


@router.get("/{product_id}/movements", response_model=StockMovementPage)
def list_product_movements(
    product_id: UUID,
    store_id: UUID,
    db: DbDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """Paginated movement ledger for one product, newest first."""
    items, total = stock_movements.list_movements(
        db, store_id=store_id, product_id=product_id, limit=limit, offset=offset
    )
    return {"items": items, "total": total}


@router.delete("/{product_id}/image", status_code=204, dependencies=[ManagerDep])
def delete_product_image(product_id: UUID, db: DbDep) -> None:
    product = products.get_product(db, product_id)
    if product is None:
        raise NotFoundError("produit", product_id)
    images.delete_product_image(db, product)


# ----------------------------------------------------------- CSV import


@router.post("/import", dependencies=[ManagerDep])
def import_products(store_id: UUID, file: UploadFile, db: DbDep):
    """Bulk import products from a CSV (semicolon-delimited, UTF-8).

    Existing products matched by barcode are updated; new ones created.
    Row-level errors never abort the batch."""
    data = file.file.read()
    return import_export.import_products_csv(db, store_id, data)
