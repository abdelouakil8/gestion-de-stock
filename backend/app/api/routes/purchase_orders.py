from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from app.api.deps import DbDep, OwnerPinDep
from app.core.exceptions import NotFoundError
from app.schemas.supplier import (
    PurchaseOrderCreate,
    PurchaseOrderRead,
    SupplierPaymentCreate,
)
from app.services import purchasing

router = APIRouter()

_OptionalUUID = Annotated[UUID | None, Query()]


@router.get("", response_model=list[PurchaseOrderRead])
def list_orders(
    db: DbDep,
    store_id: UUID,
    supplier_id: _OptionalUUID = None,
) -> list:
    return purchasing.list_orders(db, store_id, supplier_id=supplier_id)


@router.get("/{order_id}", response_model=PurchaseOrderRead)
def get_order(order_id: UUID, db: DbDep):
    order = purchasing.get_order(db, order_id)
    if order is None:
        raise NotFoundError("commande", order_id)
    return order


@router.post(
    "", response_model=PurchaseOrderRead, status_code=201, dependencies=[OwnerPinDep]
)
def create_order(payload: PurchaseOrderCreate, db: DbDep):
    return purchasing.receive_stock(db, payload)


@router.post(
    "/{order_id}/payments",
    response_model=PurchaseOrderRead,
    status_code=201,
    dependencies=[OwnerPinDep],
)
def add_payment(order_id: UUID, payload: SupplierPaymentCreate, db: DbDep):
    purchasing.record_supplier_payment(
        db, order_id, payload.amount, payload.payment_method
    )
    order = purchasing.get_order(db, order_id)
    return order
