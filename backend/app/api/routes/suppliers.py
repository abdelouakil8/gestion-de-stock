from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import DbDep, OwnerPinDep
from app.core.exceptions import NotFoundError
from app.schemas.supplier import (
    SupplierCreate,
    SupplierRead,
    SupplierUpdate,
)
from app.services import suppliers

router = APIRouter()


@router.get("", response_model=list[SupplierRead])
def list_suppliers(
    db: DbDep, store_id: UUID, q: str | None = Query(default=None)
) -> list:
    return suppliers.list_suppliers(db, store_id, q=q)


@router.get("/{supplier_id}", response_model=SupplierRead)
def get_supplier(supplier_id: UUID, db: DbDep):
    supplier = suppliers.get_supplier(db, supplier_id)
    if supplier is None:
        raise NotFoundError("fournisseur", supplier_id)
    return supplier


@router.post(
    "", response_model=SupplierRead, status_code=201, dependencies=[OwnerPinDep]
)
def create_supplier(payload: SupplierCreate, db: DbDep):
    return suppliers.create_supplier(db, payload)


@router.patch(
    "/{supplier_id}", response_model=SupplierRead, dependencies=[OwnerPinDep]
)
def update_supplier(supplier_id: UUID, payload: SupplierUpdate, db: DbDep):
    return suppliers.update_supplier(db, supplier_id, payload)


@router.delete("/{supplier_id}", status_code=204, dependencies=[OwnerPinDep])
def delete_supplier(supplier_id: UUID, db: DbDep):
    suppliers.delete_supplier(db, supplier_id)
