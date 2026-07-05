"""CSV product import — row-level errors, never aborts the whole batch.

Every row goes through the real service functions (products.create_product
or products.update_product) so pricing validation is never bypassed.
"""

import csv
import io
from decimal import Decimal, InvalidOperation
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Product
from app.schemas.product import ProductCreate, ProductUpdate
from app.services import categories, products

_REQUIRED_COLS = {"name", "price_detail", "price_gros", "price_super_gros"}
_OPTIONAL_COLS = {
    "barcode",
    "cost_price",
    "stock_quantity",
    "low_stock_threshold",
    "category",
    "supplier",
}
_ALL_COLS = _REQUIRED_COLS | _OPTIONAL_COLS


class RowError(BaseModel):
    row: int
    message: str


class ImportResult(BaseModel):
    created: int = 0
    updated: int = 0
    errors: list[RowError] = []


def _parse_decimal(value: str, field: str) -> Decimal:
    value = value.strip().replace(",", ".")
    try:
        return Decimal(value)
    except InvalidOperation:
        raise ValueError(f"{field} invalide : « {value} »") from None


def _parse_int(value: str, field: str) -> int:
    try:
        return int(value.strip())
    except ValueError:
        raise ValueError(f"{field} invalide : « {value} »") from None


def _resolve_category(
    db: Session, store_id: UUID, name: str, cache: dict[str, UUID]
) -> UUID:
    """Get or create a category by name (case-insensitive match)."""
    key = name.strip().lower()
    if key in cache:
        return cache[key]
    existing = db.scalar(
        select(Category).where(
            Category.store_id == store_id,
            Category.deleted_at.is_(None),
            Category.name.ilike(key),
        )
    )
    if existing:
        cache[key] = existing.id
        return existing.id
    cat = categories.create_category(db, store_id, name.strip())
    cache[key] = cat.id
    return cat.id


def import_products_csv(
    db: Session, store_id: UUID, file_bytes: bytes
) -> ImportResult:
    """Parse CSV and create/update products. Returns per-row results."""
    result = ImportResult()
    category_cache: dict[str, UUID] = {}

    text = file_bytes.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text), delimiter=";")

    if reader.fieldnames is None:
        result.errors.append(RowError(row=1, message="Fichier CSV vide."))
        return result

    headers = {h.strip().lower() for h in reader.fieldnames}
    missing = _REQUIRED_COLS - headers
    if missing:
        result.errors.append(
            RowError(
                row=1,
                message=f"Colonnes manquantes : {', '.join(sorted(missing))}",
            )
        )
        return result

    for row_num, raw_row in enumerate(reader, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in raw_row.items()}
        try:
            name = row.get("name", "").strip()
            if not name:
                raise ValueError("Le nom est obligatoire.")

            price_detail = _parse_decimal(row["price_detail"], "price_detail")
            price_gros = _parse_decimal(row["price_gros"], "price_gros")
            price_super_gros = _parse_decimal(
                row["price_super_gros"], "price_super_gros"
            )
            cost_price = (
                _parse_decimal(row["cost_price"], "cost_price")
                if row.get("cost_price")
                else Decimal("0.00")
            )
            stock = (
                _parse_int(row["stock_quantity"], "stock_quantity")
                if row.get("stock_quantity")
                else 0
            )
            threshold = (
                _parse_int(
                    row["low_stock_threshold"], "low_stock_threshold"
                )
                if row.get("low_stock_threshold")
                else 5
            )

            category_id = None
            if row.get("category"):
                category_id = _resolve_category(
                    db, store_id, row["category"], category_cache
                )

            barcode = row.get("barcode", "").strip() or None

            existing = None
            if barcode:
                existing = db.scalar(
                    select(Product).where(
                        Product.store_id == store_id,
                        Product.barcode == barcode,
                        Product.deleted_at.is_(None),
                    )
                )

            if existing:
                update_data = ProductUpdate(
                    name=name,
                    price_detail=price_detail,
                    price_gros=price_gros,
                    price_super_gros=price_super_gros,
                    cost_price=cost_price,
                    stock_quantity=stock,
                    low_stock_threshold=threshold,
                    category_id=category_id,
                )
                products.update_product(db, existing.id, update_data)
                result.updated += 1
            else:
                create_data = ProductCreate(
                    store_id=store_id,
                    name=name,
                    barcode=barcode,
                    price_detail=price_detail,
                    price_gros=price_gros,
                    price_super_gros=price_super_gros,
                    cost_price=cost_price,
                    stock_quantity=stock,
                    low_stock_threshold=threshold,
                    category_id=category_id,
                )
                products.create_product(db, create_data)
                result.created += 1
        except Exception as exc:
            result.errors.append(RowError(row=row_num, message=str(exc)))

    return result
