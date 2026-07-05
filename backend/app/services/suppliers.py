"""Supplier CRUD — mirrors customers.py exactly."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, SupplierPhoneExistsError
from app.core.textnorm import normalize_text
from app.models.supplier import Supplier
from app.schemas.supplier import SupplierCreate, SupplierUpdate


def create_supplier(db: Session, data: SupplierCreate) -> Supplier:
    _check_phone_unique(db, data.store_id, data.phone)
    supplier = Supplier(
        store_id=data.store_id,
        name=data.name,
        phone=data.phone,
        note=data.note,
        search_text=normalize_text(f"{data.name} {data.phone}"),
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)
    return supplier


def update_supplier(
    db: Session, supplier_id: UUID, data: SupplierUpdate
) -> Supplier:
    supplier = db.scalar(
        select(Supplier).where(
            Supplier.id == supplier_id, Supplier.deleted_at.is_(None)
        )
    )
    if supplier is None:
        raise NotFoundError("fournisseur", supplier_id)
    if data.phone is not None and data.phone != supplier.phone:
        _check_phone_unique(db, supplier.store_id, data.phone)
    updates = data.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(supplier, key, value)
    supplier.search_text = normalize_text(
        f"{supplier.name} {supplier.phone}"
    )
    db.commit()
    db.refresh(supplier)
    return supplier


def get_supplier(db: Session, supplier_id: UUID) -> Supplier | None:
    return db.scalar(
        select(Supplier).where(
            Supplier.id == supplier_id, Supplier.deleted_at.is_(None)
        )
    )


def list_suppliers(db: Session, store_id: UUID, q: str | None = None):
    stmt = (
        select(Supplier)
        .where(Supplier.store_id == store_id, Supplier.deleted_at.is_(None))
        .order_by(Supplier.name)
    )
    if q:
        normalized = normalize_text(q)
        stmt = stmt.where(Supplier.search_text.contains(normalized))
    return list(db.scalars(stmt))


def delete_supplier(db: Session, supplier_id: UUID) -> Supplier:
    from datetime import UTC, datetime

    supplier = db.scalar(
        select(Supplier).where(
            Supplier.id == supplier_id, Supplier.deleted_at.is_(None)
        )
    )
    if supplier is None:
        raise NotFoundError("fournisseur", supplier_id)
    supplier.deleted_at = datetime.now(UTC)
    db.commit()
    db.refresh(supplier)
    return supplier


def _check_phone_unique(db: Session, store_id: UUID, phone: str) -> None:
    existing = db.scalar(
        select(Supplier).where(
            Supplier.store_id == store_id,
            Supplier.phone == phone,
            Supplier.deleted_at.is_(None),
        )
    )
    if existing is not None:
        raise SupplierPhoneExistsError(phone)
