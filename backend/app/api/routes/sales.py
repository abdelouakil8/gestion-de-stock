from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query, Response

from app.api.deps import DbDep
from app.core.exceptions import NotFoundError
from app.schemas.sale import (
    AssignCustomerRequest,
    CheckoutRequest,
    PaymentCreate,
    SaleRead,
)
from app.services import customers, payments, receipts, sales, stores
from app.services import settings as settings_service

router = APIRouter()


@router.post("/checkout", response_model=SaleRead, status_code=201)
def checkout(payload: CheckoutRequest, db: DbDep):
    """Finalize a cart. Price-level resolution, the price floor (prix super
    gros), the credit rules and the atomic stock decrement are all enforced
    server-side inside one transaction — nothing from the UI is trusted."""
    return sales.finalize_sale(db, payload)


@router.get("", response_model=list[SaleRead])
def list_sales(
    db: DbDep,
    store_id: UUID,
    customer_id: UUID | None = None,
    guest: str | None = Query(default=None, pattern="^(pending|confirmed|any)$"),
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int | None = Query(default=None, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> list:
    return sales.list_sales(
        db,
        store_id,
        customer_id=customer_id,
        guest=guest,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )


@router.get("/{sale_id}", response_model=SaleRead)
def get_sale(sale_id: UUID, db: DbDep):
    sale = sales.get_sale(db, sale_id)
    if sale is None:
        raise NotFoundError("vente", sale_id)
    return sale


@router.post("/{sale_id}/payments", response_model=SaleRead, status_code=201)
def add_payment(sale_id: UUID, payload: PaymentCreate, db: DbDep):
    """Record a later payment on a sale with an outstanding balance.

    Overpayment is rejected; partial instalments and full settlement both
    work; the whole operation is atomic."""
    payments.record_payment(db, sale_id, payload.amount)
    return sales.get_sale(db, sale_id)


@router.post("/{sale_id}/customer", response_model=SaleRead)
def assign_customer(sale_id: UUID, payload: AssignCustomerRequest, db: DbDep):
    """Attach a client to a sale that has none. Rejected (409) if the sale
    already carries a customer; assigning cancels any anonymous mark."""
    return sales.assign_customer(db, sale_id, payload.customer_id)


@router.post("/{sale_id}/confirm-guest", response_model=SaleRead)
def confirm_guest(sale_id: UUID, db: DbDep):
    """Mark a walk-in sale as intentionally anonymous. Idempotent; rejected
    (409) if the sale already has a customer."""
    return sales.confirm_guest(db, sale_id)


@router.get("/{sale_id}/receipt")
def get_receipt(sale_id: UUID, db: DbDep) -> Response:
    """Printable PDF receipt for a finalized sale."""
    sale = sales.get_sale(db, sale_id)
    if sale is None:
        raise NotFoundError("vente", sale_id)
    store = stores.get_store(db, sale.store_id)
    store_settings = settings_service.get_settings(db, sale.store_id)
    customer = (
        customers.get_customer(db, sale.customer_id)
        if sale.customer_id is not None
        else None
    )
    pdf = receipts.build_receipt_pdf(sale, store, store_settings, customer)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="recu_{sale_id}.pdf"'},
    )
